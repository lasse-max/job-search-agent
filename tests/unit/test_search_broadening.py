from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from app.config import load_candidate_profile, load_company_config
from app.db import (
    _stored_evaluation_version,
    current_evaluation_policy_version,
    init_db,
    record_evaluation_skip,
    stale_open_posting_ids_for_evaluator,
    upsert_company,
    upsert_postings,
    upsert_source,
)
from app.models import JobPosting
from app.services.evaluate import (
    HYBRID_EVALUATOR_VERSION,
    _is_stretch_family,
    _role_family_fit,
    evaluate_role,
    relevance_decision,
)
from app.services.llm_evaluator import _cache_path
from app.services.benchmark import run_live_noise_benchmark
from app.services.llm_evaluator import CachedLLMProvider
import tempfile
from types import SimpleNamespace


def row(title: str, text: str = "Own cross-functional business transformation.") -> dict:
    return {
        "title": title,
        "department": "",
        "description_text": text,
        "employment_type": "",
        "locations_json": json.dumps(["London"]),
    }


class SearchBroadeningTest(unittest.TestCase):
    def test_program_and_transformation_families_are_primary(self) -> None:
        for title in (
            "Senior Program Manager",
            "Sr. Programme Manager",
            "Operations Program Manager",
            "GTM Programs Lead",
            "Programme Management Lead",
            "Programme Lead",
            "PMO Lead",
            "Process Excellence Manager",
            "Operational Excellence Lead",
            "Digital Transformation Manager",
            "Enterprise Transformation Office",
            "Continuous Improvement Manager",
            "Change Management Lead",
        ):
            with self.subTest(title=title):
                posting = row(title)
                self.assertTrue(relevance_decision(posting, load_company_config()).should_evaluate)
                self.assertFalse(_is_stretch_family(title, "", posting["description_text"]))
                self.assertEqual(_role_family_fit(title, "", posting["description_text"]), 92)

    def test_engineering_program_scope_cannot_be_promoted_by_generic_program_patterns(self) -> None:
        for title in (
            "Technical Program Manager",
            "Technical Programme Manager",
            "TPM",
            "Engineering Program Manager",
            "Software Programme Manager",
            "Hardware Program Manager",
            "Release Manager",
            "Delivery Manager",
            "Senior Program Manager",
        ):
            with self.subTest(title=title):
                pure = row(title, "Own SDLC release trains and software delivery.")
                self.assertFalse(relevance_decision(pure, load_company_config()).should_evaluate)
                evaluation = evaluate_role(pure, load_company_config(), use_env_provider=False)
                self.assertLess(evaluation.role_fit_score, 60)
                business = row(
                    title, "Own SDLC delivery and cross-functional business transformation."
                )
                self.assertTrue(relevance_decision(business, load_company_config()).should_evaluate)
                self.assertTrue(_is_stretch_family(title, "", business["description_text"]))
                self.assertEqual(_role_family_fit(title, "", business["description_text"]), 78)

    def test_manufacturing_ci_reaches_judgment_not_a_gate_exclusion(self) -> None:
        for title in ("Plant Continuous Improvement Manager", "Process Excellence Lead"):
            self.assertTrue(
                relevance_decision(
                    row(title, "Lead Lean Six Sigma improvements on the factory production line."),
                    load_company_config(),
                ).should_evaluate
            )

    def test_profile_bump_reopens_only_fresh_versioned_gate_skips(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        company = load_company_config()
        company_id = upsert_company(conn, company)
        source_id = upsert_source(conn, company_id, company)
        for key, posted_at in (("fresh", "2026-09-14"), ("old", "2026-07-01")):
            result = upsert_postings(
                conn,
                company_id,
                source_id,
                [
                    JobPosting(
                        company=company.name,
                        title="Senior Program Manager",
                        locations=["London"],
                        department="Business",
                        employment_type="Full time",
                        description_text=key,
                        source_type=company.ats_type,
                        source_url=f"https://example.com/{key}",
                        source_job_id=key,
                        source_posted_at=posted_at,
                        raw_payload_hash=key,
                        canonical_key=key,
                    )
                ],
                "2026-09-14",
            )
            with patch(
                "app.db.load_candidate_profile",
                return_value=replace(
                    load_candidate_profile(),
                    version="previous-profile",
                ),
            ):
                record_evaluation_skip(
                    conn,
                    result.new_posting_ids[0],
                    key,
                    "excluded_title_department_function",
                    evaluator_version=current_evaluation_policy_version(HYBRID_EVALUATOR_VERSION),
                )
                self.assertEqual(
                    stale_open_posting_ids_for_evaluator(
                        conn,
                        source_id,
                        evaluator_version=HYBRID_EVALUATOR_VERSION,
                        limit=100,
                        recency_cutoff="2026-08-25",
                    ),
                    [],
                )
        ids = stale_open_posting_ids_for_evaluator(
            conn,
            source_id,
            evaluator_version=HYBRID_EVALUATOR_VERSION,
            limit=100,
            recency_cutoff="2026-08-25",
        )
        self.assertEqual(len(ids), 1)
        self.assertEqual(
            conn.execute(
                "SELECT source_job_id FROM job_postings WHERE id = ?",
                (ids[0],),
            ).fetchone()[0],
            "fresh",
        )
        conn.close()

    def test_live_cache_identity_includes_profile_version(self) -> None:
        first = _cache_path(Path("cache"), "model", row("Program Manager"), profile_version="v3")
        second = _cache_path(Path("cache"), "model", row("Program Manager"), profile_version="v4")
        self.assertNotEqual(first, second)

    def test_profile_bump_has_distinct_persistence_identity_and_same_calibrated_suffix(self) -> None:
        versions = []
        for profile in ("previous-profile", load_candidate_profile().version):
            versions.append(_stored_evaluation_version(SimpleNamespace(provenance={
                "model_version": "claude-haiku-4-5", "evaluator_version": HYBRID_EVALUATOR_VERSION,
                "candidate_profile_version": profile, "prompt_version": "role_evaluation_v7",
            })))
        self.assertNotEqual(*versions)
        self.assertTrue(all(v.endswith(f"|{HYBRID_EVALUATOR_VERSION}") for v in versions))

    def test_negated_business_context_does_not_rescue_delivery(self) -> None:
        posting = row("Release Manager", "Own SDLC releases, not commercial operations programs.")
        self.assertFalse(relevance_decision(posting, load_company_config()).should_evaluate)
        self.assertFalse(_is_stretch_family(posting["title"], "", posting["description_text"]))

    def test_fresh_claude_scope_challenge_preserves_recall_without_plant_noise(self) -> None:
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            run = run_live_noise_benchmark(
                live_noise_set_path=root / "data/evaluation_set/search_broadening_set.yaml",
                report_dir=Path(directory), label_set_purpose="synthetic_scope_challenge",
                llm_provider=CachedLLMProvider(cache_dir=root / "data/fixtures/search_broadening_llm"),
            )
        self.assertEqual(run.metrics.labelled_roles, 9)
        self.assertTrue(run.metrics.passes)
        for result in run.results:
            with self.subTest(role=result.role_id):
                if result.expected_recommendation == "skip":
                    self.assertLess(result.fit_score, 60)
                    self.assertEqual(result.actual_recommendation, "skip")
