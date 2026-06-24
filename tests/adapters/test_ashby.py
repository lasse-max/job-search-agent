from __future__ import annotations

from pathlib import Path
import unittest

from app.adapters.ashby import AshbyAdapter
from app.config import load_company_config


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "ashby"


class AshbyAdapterTest(unittest.TestCase):
    def test_normalizes_airwallex_fixture(self) -> None:
        company = load_company_config("Airwallex")
        adapter = AshbyAdapter()
        result = adapter.fetch_from_file(
            company.source_key,
            str(FIXTURE_DIR / "airwallex_jobs.json"),
        )

        health = adapter.health_check(result)
        postings = adapter.normalize(result, company)

        self.assertEqual(health.status, "healthy")
        self.assertEqual(health.fetched_count, 3)
        self.assertEqual(
            postings[0].source_job_id,
            "f8d368e7-9d5f-424f-bf3a-b28435172e52",
        )
        self.assertEqual(
            postings[0].title,
            "Manager, Revenue Strategy & Enablement, SG & SEA",
        )
        self.assertEqual(postings[0].department, "Strategy & Operations")
        self.assertEqual(postings[0].employment_type, "FullTime")
        self.assertIn("SG - Singapore", postings[0].locations)
        self.assertIn("founder-like energy", postings[0].description_text)
        self.assertEqual(postings[0].source_type, "ashby")
        self.assertTrue(postings[0].source_url.startswith("https://jobs.ashbyhq.com/"))
        self.assertEqual(adapter.identity({"id": "ashby-id"}), "ashby-id")

    def test_zero_job_response_is_healthy(self) -> None:
        company = load_company_config("Airwallex")
        adapter = AshbyAdapter()
        result = adapter.fetch_from_file(company.source_key, str(FIXTURE_DIR / "zero_jobs.json"))

        health = adapter.health_check(result)
        postings = adapter.normalize(result, company)

        self.assertEqual(health.status, "healthy")
        self.assertEqual(health.fetched_count, 0)
        self.assertEqual(postings, [])

    def test_malformed_payload_fails_loudly(self) -> None:
        company = load_company_config("Airwallex")
        adapter = AshbyAdapter()
        result = adapter.fetch_from_file(
            company.source_key,
            str(FIXTURE_DIR / "malformed_jobs.json"),
        )

        health = adapter.health_check(result)

        self.assertEqual(health.status, "failing")
        self.assertIn("jobs array", health.error_summary or "")

    def test_normalizes_secondary_and_postal_locations(self) -> None:
        company = load_company_config("Airwallex")
        adapter = AshbyAdapter()
        result = adapter.fetch_from_file(
            company.source_key,
            str(FIXTURE_DIR / "location_variants.json"),
        )

        postings = adapter.normalize(result, company)
        by_id = {posting.source_job_id: posting for posting in postings}

        self.assertEqual(
            by_id["ashby-secondary-location"].locations,
            ["AU - Melbourne", "AU - Sydney"],
        )
        self.assertEqual(
            by_id["ashby-postal-only"].locations,
            ["London, England, United Kingdom"],
        )


if __name__ == "__main__":
    unittest.main()
