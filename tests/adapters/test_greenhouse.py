from __future__ import annotations

from pathlib import Path
import unittest

from app.adapters.greenhouse import GreenhouseAdapter
from app.config import load_company_config


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "greenhouse"


class GreenhouseAdapterTest(unittest.TestCase):
    def test_normalizes_databricks_fixture(self) -> None:
        company = load_company_config("Databricks")
        adapter = GreenhouseAdapter()
        result = adapter.fetch_from_file(
            company.source_key,
            str(FIXTURE_DIR / "databricks_jobs.json"),
        )

        health = adapter.health_check(result)
        postings = adapter.normalize(result, company)

        self.assertEqual(health.status, "healthy")
        self.assertEqual(health.fetched_count, 3)
        self.assertEqual(postings[0].source_job_id, "8516118002")
        self.assertEqual(postings[0].title, "Deployment Strategist")
        self.assertIn("Sydney, Australia", postings[0].locations)
        self.assertIn("cross-functional", postings[0].description_text)
        self.assertEqual(postings[0].source_type, "greenhouse")

    def test_zero_job_response_is_healthy(self) -> None:
        company = load_company_config("Databricks")
        adapter = GreenhouseAdapter()
        result = adapter.fetch_from_file(company.source_key, str(FIXTURE_DIR / "zero_jobs.json"))

        health = adapter.health_check(result)
        postings = adapter.normalize(result, company)

        self.assertEqual(health.status, "healthy")
        self.assertEqual(health.fetched_count, 0)
        self.assertEqual(postings, [])

    def test_malformed_payload_fails_loudly(self) -> None:
        company = load_company_config("Databricks")
        adapter = GreenhouseAdapter()
        result = adapter.fetch_from_file(
            company.source_key,
            str(FIXTURE_DIR / "malformed_jobs.json"),
        )

        health = adapter.health_check(result)

        self.assertEqual(health.status, "failing")
        self.assertIn("jobs array", health.error_summary or "")


if __name__ == "__main__":
    unittest.main()
