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

        self.assertEqual(
            source_endpoint("smartrecruiters", "Grab"),
            "https://api.smartrecruiters.com/v1/companies/Grab/postings?limit=100&offset=0",
        )
        self.assertEqual(parser_version("smartrecruiters"), "smartrecruiters_v1")

    def test_bounded_rollout_keeps_unaudited_or_dead_feeds_disabled(self) -> None:
        companies = load_watchlist()
        ashby_companies = {
            str(company["name"]): bool(company["enabled"])
            for company in companies
            if company.get("ats_type") == "ashby"
        }
        disabled_greenhouse = [
            str(company["name"])
            for company in companies
            if company.get("ats_type") == "greenhouse" and not bool(company["enabled"])
        ]
        disabled_lever = [
            str(company["name"])
            for company in companies
            if company.get("ats_type") == "lever" and not bool(company["enabled"])
        ]
        disabled_smartrecruiters = [
            str(company["name"])
            for company in companies
            if company.get("ats_type") == "smartrecruiters" and not bool(company["enabled"])
        ]
        enabled_unsupported = [
            str(company["name"])
            for company in companies
            if bool(company["enabled"])
            and company.get("ats_type")
            not in {"greenhouse", "ashby", "lever", "smartrecruiters"}
        ]

        self.assertTrue(ashby_companies["OpenAI"])
        self.assertTrue(ashby_companies["Airwallex"])
        self.assertTrue(ashby_companies["Sierra"])
        self.assertEqual(disabled_greenhouse, [])
        self.assertEqual(disabled_lever, ["Atlassian", "SafetyCulture"])
        self.assertEqual(
            disabled_smartrecruiters,
            ["Wise", "Grab", "ServiceNow / Moveworks", "Nearmap", "Delivery Hero"],
        )
        self.assertEqual(enabled_unsupported, [])
        by_name = {company["name"]: company for company in companies}
        for name in ("DoorDash", "Canva", "Glean", "DeepL", "Magentic"):
            self.assertTrue(by_name[name]["enabled"])
            self.assertGreater(by_name[name]["job_count_at_audit"], 0)
        self.assertEqual(by_name["SafetyCulture"]["job_count_at_audit"], 0)


if __name__ == "__main__":
    unittest.main()
