from __future__ import annotations

from dataclasses import dataclass
import io
from pathlib import Path
import unittest
import urllib.error
from unittest.mock import patch

from app.adapters import get_adapter
from app.config import load_company_config


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class FailLoudCase:
    company_name: str
    source_type: str
    malformed_json_fixture: Path
    invalid_posting_fixture: Path


CASES = (
    FailLoudCase(
        company_name="Databricks",
        source_type="greenhouse",
        malformed_json_fixture=ROOT / "data" / "fixtures" / "greenhouse" / "malformed_json.json",
        invalid_posting_fixture=ROOT / "data" / "fixtures" / "greenhouse" / "invalid_posting.json",
    ),
    FailLoudCase(
        company_name="Airwallex",
        source_type="ashby",
        malformed_json_fixture=ROOT / "data" / "fixtures" / "ashby" / "malformed_json.json",
        invalid_posting_fixture=ROOT / "data" / "fixtures" / "ashby" / "invalid_posting.json",
    ),
    FailLoudCase(
        company_name="Mistral AI",
        source_type="lever",
        malformed_json_fixture=ROOT / "data" / "fixtures" / "lever" / "malformed_json.json",
        invalid_posting_fixture=ROOT / "data" / "fixtures" / "lever" / "invalid_posting.json",
    ),
    FailLoudCase(
        company_name="Grab",
        source_type="smartrecruiters",
        malformed_json_fixture=(
            ROOT / "data" / "fixtures" / "smartrecruiters" / "malformed_json.json"
        ),
        invalid_posting_fixture=(
            ROOT / "data" / "fixtures" / "smartrecruiters" / "invalid_posting.json"
        ),
    ),
)


class FailLoudContractTest(unittest.TestCase):
    def test_malformed_json_syntax_fails_loudly_for_all_adapters(self) -> None:
        for case in CASES:
            with self.subTest(adapter=case.source_type):
                company = load_company_config(case.company_name)
                adapter = get_adapter(case.source_type)
                result = adapter.fetch_from_file(
                    company.source_key,
                    str(case.malformed_json_fixture),
                )

                health = adapter.health_check(result)

                self.assertEqual(health.status, "failing")
                self.assertIn("malformed JSON", health.error_summary or "")
                with self.assertRaises(ValueError):
                    adapter.normalize(result, company)

    def test_invalid_idless_posting_fails_loudly_for_all_adapters(self) -> None:
        for case in CASES:
            with self.subTest(adapter=case.source_type):
                company = load_company_config(case.company_name)
                adapter = get_adapter(case.source_type)
                result = adapter.fetch_from_file(
                    company.source_key,
                    str(case.invalid_posting_fixture),
                )

                health = adapter.health_check(result)

                self.assertEqual(health.status, "failing")
                self.assertIn("invalid posting", health.error_summary or "")
                with self.assertRaises(ValueError):
                    adapter.normalize(result, company)

    def test_http_error_fetch_fails_loudly_for_all_adapters(self) -> None:
        for case in CASES:
            with self.subTest(adapter=case.source_type):
                company = load_company_config(case.company_name)
                adapter = get_adapter(case.source_type)
                http_error = urllib.error.HTTPError(
                    url="https://example.invalid/jobs",
                    code=500,
                    msg="server error",
                    hdrs={},
                    fp=io.BytesIO(b"upstream exploded"),
                )

                with patch("urllib.request.urlopen", side_effect=http_error):
                    result = adapter.fetch(company.source_key)

                health = adapter.health_check(result)

                self.assertEqual(result.status, "failure")
                self.assertEqual(result.http_status, 500)
                self.assertEqual(health.status, "failing")
                self.assertIn("server error", health.error_summary or "")

    def test_timeout_fetch_fails_loudly_for_all_adapters(self) -> None:
        for case in CASES:
            with self.subTest(adapter=case.source_type):
                company = load_company_config(case.company_name)
                adapter = get_adapter(case.source_type)

                with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
                    result = adapter.fetch(company.source_key)

                health = adapter.health_check(result)

                self.assertEqual(result.status, "failure")
                self.assertIsNone(result.http_status)
                self.assertEqual(health.status, "failing")
                self.assertIn("timed out", health.error_summary or "")


if __name__ == "__main__":
    unittest.main()
