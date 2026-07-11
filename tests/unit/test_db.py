from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace
import unittest

from app.db import (
    _stored_evaluation_version,
    init_db,
    record_evaluation_skip,
    upsert_company,
    upsert_postings,
    upsert_source,
)
from app.models import CompanyConfig, JobPosting


class JobPostingPersistenceTest(unittest.TestCase):
    def test_init_db_adds_version_marker_to_legacy_evaluation_skips(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE evaluation_skips (
              id INTEGER PRIMARY KEY,
              job_posting_id INTEGER NOT NULL,
              input_hash TEXT NOT NULL,
              reason TEXT NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE(job_posting_id, input_hash, reason)
            )
            """
        )

        init_db(conn)

        columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(evaluation_skips)").fetchall()
        }
        self.assertIn("evaluator_version", columns)

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

    def test_same_title_roles_with_shared_long_boilerplate_remain_distinct(self) -> None:
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
            target_locations=["London"],
            target_role_family_notes="Strategy and operations",
            warm_path=False,
        )
        company_id = upsert_company(conn, company)
        source_id = upsert_source(conn, company_id, company)
        boilerplate = (
            "ExampleCo builds trusted infrastructure for teams around the world. "
            "Our people work across functions, markets, and time zones to solve "
            "difficult customer problems with care, curiosity, and sound judgment. "
            "We value thoughtful execution, inclusive collaboration, clear ownership, "
            "and durable outcomes. Everyone contributes to a culture of learning and "
            "continuous improvement while helping the company scale responsibly. "
            "This introduction is intentionally long enough to exceed the old four "
            "hundred character deduplication shortcut before the actual role scope. "
        )
        self.assertGreater(len(boilerplate), 470)

        result = upsert_postings(
            conn,
            company_id,
            source_id,
            [
                _posting(
                    "strategy-planning",
                    ["London, United Kingdom"],
                    title="Strategy Manager",
                    description_text=(
                        f"{boilerplate} Own annual planning, investment governance, "
                        "and executive operating reviews."
                    ),
                ),
                _posting(
                    "strategy-partners",
                    ["London, United Kingdom"],
                    title="Strategy Manager",
                    description_text=(
                        f"{boilerplate} Build the partner expansion model, negotiate "
                        "channel programs, and lead regional launch execution."
                    ),
                ),
            ],
            "2026-07-11T08:00:00+00:00",
        )

        rows = conn.execute(
            "SELECT source_job_id, description_text FROM job_postings ORDER BY source_job_id"
        ).fetchall()
        self.assertEqual(len(result.new_posting_ids), 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {row["source_job_id"] for row in rows},
            {"strategy-partners", "strategy-planning"},
        )
        self.assertTrue(any("annual planning" in row["description_text"] for row in rows))
        self.assertTrue(any("partner expansion" in row["description_text"] for row in rows))

    def test_stored_evaluation_version_includes_hybrid_calibration(self) -> None:
        llm_evaluation = SimpleNamespace(
            provenance={
                "model_version": "claude-haiku-4-5",
                "evaluator_version": "hybrid_claude_v3",
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
            "claude-haiku-4-5|hybrid_claude_v3",
        )
        self.assertEqual(
            _stored_evaluation_version(fallback_evaluation),
            "deterministic_fallback_v1",
        )

    def test_material_change_clears_only_versioned_gate_skip(self) -> None:
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
            target_locations=["London"],
            target_role_family_notes="Strategy and operations",
            warm_path=False,
        )
        company_id = upsert_company(conn, company)
        source_id = upsert_source(conn, company_id, company)
        first = upsert_postings(
            conn,
            company_id,
            source_id,
            [_posting("job-1", ["London, United Kingdom"])],
            "2026-07-11T08:00:00+00:00",
        )
        job_id = first.new_posting_ids[0]
        record_evaluation_skip(
            conn,
            job_id,
            "input-a",
            "excluded_title_department_function",
            evaluator_version="hybrid_claude_v3",
        )
        record_evaluation_skip(
            conn,
            job_id,
            "input-a",
            "llm_evaluation_dropped: test",
        )

        upsert_postings(
            conn,
            company_id,
            source_id,
            [
                _posting(
                    "job-1",
                    ["London, United Kingdom"],
                    description_text="Materially changed strategy and operations scope.",
                )
            ],
            "2026-07-11T09:00:00+00:00",
        )

        rows = conn.execute(
            "SELECT evaluator_version, reason FROM evaluation_skips ORDER BY id"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["evaluator_version"])
        self.assertEqual(rows[0]["reason"], "llm_evaluation_dropped: test")

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
            ["Munich, Germany"],
        )
        self.assertTrue(str(rows[0]["source_job_id"]).startswith("multi-"))

    def test_location_suffix_variants_merge_with_different_descriptions(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        company = CompanyConfig(
            name="MistralLike",
            tier=2,
            enabled=True,
            ats_type="lever",
            source_key="mistrallike",
            careers_url="https://example.com/careers",
            target_locations=["London", "Munich", "Singapore"],
            target_role_family_notes="AI deployment strategy",
            warm_path=False,
        )
        company_id = upsert_company(conn, company)
        source_id = upsert_source(conn, company_id, company)
        postings = [
            _posting(
                "ds-london",
                ["London, United Kingdom"],
                title="AI Deployment Strategist - London",
                description_text=(
                    "Lead customer strategy, executive discovery, and AI deployment "
                    "across the United Kingdom."
                ),
            ),
            _posting(
                "ds-munich",
                ["Munich, Germany"],
                title="AI Deployment Strategist - Munich",
                description_text=(
                    "Lead customer strategy, executive discovery, and AI deployment "
                    "across Germany."
                ),
            ),
            _posting(
                "ds-singapore",
                ["Singapore"],
                title="AI Deployment Strategist - Singapore",
                description_text=(
                    "Lead customer strategy, executive discovery, and AI deployment "
                    "across Singapore."
                ),
            ),
        ]

        first = upsert_postings(
            conn,
            company_id,
            source_id,
            postings,
            "2026-07-11T08:00:00+00:00",
        )
        replay = upsert_postings(
            conn,
            company_id,
            source_id,
            postings,
            "2026-07-11T09:00:00+00:00",
        )

        rows = conn.execute("SELECT * FROM job_postings").fetchall()
        self.assertEqual(len(first.new_posting_ids), 1)
        self.assertEqual(replay.new_posting_ids, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "AI Deployment Strategist")
        self.assertEqual(
            json.loads(rows[0]["locations_json"]),
            ["London, United Kingdom", "Munich, Germany", "Singapore"],
        )

    def test_functional_title_suffixes_remain_distinct(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        company = CompanyConfig(
            name="ExampleCo",
            tier=2,
            enabled=True,
            ats_type="lever",
            source_key="example",
            careers_url="https://example.com/careers",
            target_locations=["Paris"],
            target_role_family_notes="AI deployment strategy",
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
                    "ds-general",
                    ["Paris, France"],
                    title="AI Deployment Strategist - Paris",
                ),
                _posting(
                    "ds-cyber",
                    ["Paris, France"],
                    title="AI Deployment Strategist - Cybersecurity",
                ),
            ],
            "2026-07-11T08:00:00+00:00",
        )

        self.assertEqual(len(result.new_posting_ids), 2)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM job_postings").fetchone()[0],
            2,
        )

    def test_location_variants_with_different_blocker_risk_remain_distinct(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        company = CompanyConfig(
            name="MistralLike",
            tier=2,
            enabled=True,
            ats_type="lever",
            source_key="mistrallike",
            careers_url="https://example.com/careers",
            target_locations=["London", "Singapore"],
            target_role_family_notes="AI deployment strategy",
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
                    "ds-london",
                    ["London, United Kingdom"],
                    title="AI Deployment Strategist - London",
                    description_text="Lead executive discovery and business transformation.",
                ),
                _posting(
                    "ds-singapore",
                    ["Singapore"],
                    title="AI Deployment Strategist - Singapore",
                    description_text=(
                        "Production coding and advanced Python programming are required."
                    ),
                ),
            ],
            "2026-07-11T08:00:00+00:00",
        )

        self.assertEqual(len(result.new_posting_ids), 2)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM job_postings").fetchone()[0], 2)

    def test_near_identical_location_variants_keep_required_ai_depth_distinct(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        company = CompanyConfig(
            name="MistralLike",
            tier=2,
            enabled=True,
            ats_type="lever",
            source_key="mistrallike",
            careers_url="https://example.com/careers",
            target_locations=["London", "Munich"],
            target_role_family_notes="AI deployment strategy",
            warm_path=False,
        )
        company_id = upsert_company(conn, company)
        source_id = upsert_source(conn, company_id, company)
        common = (
            "Lead executive discovery, map customer workflows, build transformation "
            "roadmaps, align senior stakeholders, and own deployment outcomes across "
            "complex enterprise programs. Partner with product and engineering teams "
            "to translate business needs into practical adoption plans."
        )

        result = upsert_postings(
            conn,
            company_id,
            source_id,
            [
                _posting(
                    "ds-london",
                    ["London, United Kingdom"],
                    title="AI Deployment Strategist - London",
                    description_text=common,
                ),
                _posting(
                    "ds-munich",
                    ["Munich, Germany"],
                    title="AI Deployment Strategist - Munich",
                    description_text=(
                        f"{common} Hands-on experience building and deploying AI "
                        "applications is required."
                    ),
                ),
            ],
            "2026-07-11T08:00:00+00:00",
        )

        self.assertEqual(len(result.new_posting_ids), 2)
        rows = conn.execute(
            "SELECT source_job_id, description_text FROM job_postings ORDER BY source_job_id"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(any("AI applications is required" in row["description_text"] for row in rows))
        self.assertTrue(any("AI applications is required" not in row["description_text"] for row in rows))

    def test_location_variants_with_different_seniority_remain_distinct(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        company = CompanyConfig(
            name="ExampleCo",
            tier=2,
            enabled=True,
            ats_type="lever",
            source_key="example",
            careers_url="https://example.com/careers",
            target_locations=["London", "Munich"],
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
                _posting(
                    "strategy-london",
                    ["London, United Kingdom"],
                    title="Strategy Manager - London",
                    description_text=(
                        "Lead global strategy planning and executive operating cadence. "
                        "Requires 5 years of relevant experience as an individual contributor."
                    ),
                ),
                _posting(
                    "strategy-munich",
                    ["Munich, Germany"],
                    title="Strategy Manager - Munich",
                    description_text=(
                        "Lead global strategy planning and executive operating cadence. "
                        "Requires 15 years of relevant experience and manage a team of managers."
                    ),
                ),
            ],
            "2026-07-11T08:00:00+00:00",
        )

        self.assertEqual(len(result.new_posting_ids), 2)
        rows = conn.execute(
            "SELECT source_job_id, description_text FROM job_postings ORDER BY source_job_id"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(any("5 years" in row["description_text"] for row in rows))
        self.assertTrue(any("15 years" in row["description_text"] for row in rows))


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
