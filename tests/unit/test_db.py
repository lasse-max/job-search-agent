from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace
import unittest

from app.db import (
    _stored_evaluation_version,
    init_db,
    upsert_company,
    upsert_postings,
    upsert_source,
)
from app.models import CompanyConfig, JobPosting


class JobPostingPersistenceTest(unittest.TestCase):
    def test_multi_location_variants_merge_into_one_open_posting(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        company = CompanyConfig(
            name="ExampleCo",
            tier=1,
            enabled=True,
            ats_type="greenhouse",
            source_key="example",
            careers_url="https://example.com/careers",
            target_locations=["London", "Paris", "Berlin"],
            target_role_family_notes="Strategy and operations",
            warm_path=False,
        )
        company_id = upsert_company(conn, company)
        source_id = upsert_source(conn, company_id, company)

        result = upsert_postings(
            conn,
            company_id,
            source_id,
            [
                _posting("job-london", ["London, United Kingdom"]),
                _posting("job-paris", ["Paris, France"]),
                _posting("job-berlin", ["Berlin, Germany", "Paris, France"]),
            ],
            "2026-06-29T08:00:00+00:00",
        )

        rows = conn.execute("SELECT * FROM job_postings").fetchall()
        self.assertEqual(len(result.new_posting_ids), 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            json.loads(rows[0]["locations_json"]),
            [
                "London, United Kingdom",
                "Paris, France",
                "Berlin, Germany",
            ],
        )
        self.assertTrue(str(rows[0]["source_job_id"]).startswith("multi-"))

    def test_stored_evaluation_version_includes_hybrid_calibration(self) -> None:
        llm_evaluation = SimpleNamespace(
            provenance={
                "model_version": "claude-haiku-4-5",
                "evaluator_version": "hybrid_claude_v2",
            }
        )
        fallback_evaluation = SimpleNamespace(
            provenance={
                "model_version": "deterministic_fallback_v1",
                "evaluator_version": "deterministic_fallback_v1",
            }
        )

        self.assertEqual(
            _stored_evaluation_version(llm_evaluation),
            "claude-haiku-4-5|hybrid_claude_v2",
        )
        self.assertEqual(
            _stored_evaluation_version(fallback_evaluation),
            "deterministic_fallback_v1",
        )

    def test_language_variants_merge_and_prefer_supported_language_variant(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        company = CompanyConfig(
            name="SierraLike",
            tier=1,
            enabled=True,
            ats_type="ashby",
            source_key="sierralike",
            careers_url="https://example.com/careers",
            target_locations=["London", "Paris", "Madrid"],
            target_role_family_notes="Agent strategy",
            warm_path=False,
        )
        company_id = upsert_company(conn, company)
        source_id = upsert_source(conn, company_id, company)

        result = upsert_postings(
            conn,
            company_id,
            source_id,
            [
                _posting(
                    "job-french",
                    ["Paris, France"],
                    title="Strategist, Agent Development (French speaking)",
                    description_text="Lead agent strategy for customers.",
                ),
                _posting(
                    "job-german",
                    ["Munich, Germany"],
                    title="Strategist, Agent Development (German speaking)",
                    description_text="Lead agent strategy for customers.",
                ),
                _posting(
                    "job-spanish",
                    ["Madrid, Spain"],
                    title="Strategist, Agent Development (Spanish speaking)",
                    description_text="Lead agent strategy for customers.",
                ),
            ],
            "2026-06-30T08:00:00+00:00",
        )

        rows = conn.execute("SELECT * FROM job_postings").fetchall()
        self.assertEqual(len(result.new_posting_ids), 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Strategist, Agent Development (German speaking)")
        self.assertEqual(rows[0]["source_url"], "https://example.com/jobs/job-german")
        self.assertEqual(
            json.loads(rows[0]["locations_json"]),
            ["Paris, France", "Munich, Germany", "Madrid, Spain"],
        )
        self.assertTrue(str(rows[0]["source_job_id"]).startswith("multi-"))


def _posting(
    source_job_id: str,
    locations: list[str],
    *,
    title: str = "AWS Cloud Partner Solutions Architect - EMEA",
    description_text: str = "Lead partner solution strategy across EMEA cloud transformation.",
) -> JobPosting:
    return JobPosting(
        company="ExampleCo",
        title=title,
        locations=locations,
        department="Partner Solutions",
        employment_type="Full-time",
        description_text=description_text,
        source_type="greenhouse",
        source_url=f"https://example.com/jobs/{source_job_id}",
        source_job_id=source_job_id,
        source_posted_at="2026-06-29",
        raw_payload_hash=f"hash-{source_job_id}",
        canonical_key=f"example-{source_job_id}",
    )


if __name__ == "__main__":
    unittest.main()
