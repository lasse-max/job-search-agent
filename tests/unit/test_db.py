from __future__ import annotations

import json
import sqlite3
import unittest

from app.db import init_db, upsert_company, upsert_postings, upsert_source
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


def _posting(source_job_id: str, locations: list[str]) -> JobPosting:
    return JobPosting(
        company="ExampleCo",
        title="AWS Cloud Partner Solutions Architect - EMEA",
        locations=locations,
        department="Partner Solutions",
        employment_type="Full-time",
        description_text="Lead partner solution strategy across EMEA cloud transformation.",
        source_type="greenhouse",
        source_url=f"https://example.com/jobs/{source_job_id}",
        source_job_id=source_job_id,
        source_posted_at="2026-06-29",
        raw_payload_hash=f"hash-{source_job_id}",
        canonical_key=f"example-{source_job_id}",
    )


if __name__ == "__main__":
    unittest.main()
