from __future__ import annotations

import unittest

from app.adapters import parser_version, source_endpoint
from app.config import load_watchlist


class SourceConfigTest(unittest.TestCase):
    def test_source_metadata_is_derived_from_ats_type(self) -> None:
        self.assertEqual(
            source_endpoint("greenhouse", "databricks"),
            "https://boards-api.greenhouse.io/v1/boards/databricks/jobs?content=true",
        )
        self.assertEqual(parser_version("greenhouse"), "greenhouse_v1")

        self.assertEqual(
            source_endpoint("ashby", "airwallex"),
            "https://api.ashbyhq.com/posting-api/job-board/airwallex"
            "?includeCompensation=false",
        )
        self.assertEqual(parser_version("ashby"), "ashby_v1")

        self.assertEqual(
            source_endpoint("lever", "mistral"),
            "https://api.lever.co/v0/postings/mistral?mode=json",
        )
        self.assertEqual(parser_version("lever"), "lever_v1")

    def test_ashby_companies_enabled_and_lever_companies_disabled(self) -> None:
        companies = load_watchlist()
        ashby_companies = {
            str(company["name"]): bool(company["enabled"])
            for company in companies
            if company.get("ats_type") == "ashby"
        }
        lever_companies = [
            str(company["name"])
            for company in companies
            if company.get("ats_type") == "lever" and bool(company["enabled"])
        ]

        self.assertTrue(ashby_companies["OpenAI"])
        self.assertTrue(ashby_companies["Airwallex"])
        self.assertTrue(ashby_companies["Sierra"])
        self.assertEqual(lever_companies, [])


if __name__ == "__main__":
    unittest.main()
