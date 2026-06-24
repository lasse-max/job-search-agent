from __future__ import annotations

from pathlib import Path
import unittest

from app.adapters.lever import LeverAdapter
from app.config import load_company_config


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "lever"


class LeverAdapterTest(unittest.TestCase):
    def test_normalizes_mistral_fixture(self) -> None:
        company = load_company_config("Mistral AI")
        adapter = LeverAdapter()
        result = adapter.fetch_from_file(
            company.source_key,
            str(FIXTURE_DIR / "mistral_jobs.json"),
        )

        health = adapter.health_check(result)
        postings = adapter.normalize(result, company)

        self.assertEqual(health.status, "healthy")
        self.assertEqual(health.fetched_count, 3)
        self.assertEqual(
            postings[0].source_job_id,
            "1937a5af-2c9b-4a75-bb91-b06ebe714dbd",
        )
        self.assertEqual(postings[0].title, "AI Deployment Strategist - Munich, Germany")
        self.assertEqual(postings[0].department, "Solutions")
        self.assertEqual(postings[0].employment_type, "Full-time")
        self.assertIn("Munich", postings[0].locations)
        self.assertIn("AI Deployment Strategist", postings[0].description_text)
        self.assertEqual(postings[0].source_type, "lever")
        self.assertTrue(postings[0].source_url.startswith("https://jobs.lever.co/mistral/"))
        self.assertEqual(postings[0].source_posted_at, "2024-12-16T16:40:35+00:00")
        self.assertEqual(
            adapter.identity({"id": "1937a5af-2c9b-4a75-bb91-b06ebe714dbd"}),
            "1937a5af-2c9b-4a75-bb91-b06ebe714dbd",
        )

    def test_zero_job_response_is_healthy(self) -> None:
        company = load_company_config("Mistral AI")
        adapter = LeverAdapter()
        result = adapter.fetch_from_file(company.source_key, str(FIXTURE_DIR / "zero_jobs.json"))

        health = adapter.health_check(result)
        postings = adapter.normalize(result, company)

        self.assertEqual(health.status, "healthy")
        self.assertEqual(health.fetched_count, 0)
        self.assertEqual(postings, [])

    def test_malformed_payload_fails_loudly(self) -> None:
        company = load_company_config("Mistral AI")
        adapter = LeverAdapter()
        result = adapter.fetch_from_file(
            company.source_key,
            str(FIXTURE_DIR / "malformed_jobs.json"),
        )

        health = adapter.health_check(result)

        self.assertEqual(health.status, "failing")
        self.assertIn("postings array", health.error_summary or "")

    def test_all_locations_are_preserved(self) -> None:
        company = load_company_config("Mistral AI")
        adapter = LeverAdapter()
        result = adapter.fetch_from_file(
            company.source_key,
            str(FIXTURE_DIR / "mistral_jobs.json"),
        )

        postings = adapter.normalize(result, company)
        emea = next(posting for posting in postings if "AI4Engineering" in posting.title)

        self.assertEqual(
            emea.locations,
            ["Paris", "London", "Munich", "Madrid", "Amsterdam"],
        )


if __name__ == "__main__":
    unittest.main()
