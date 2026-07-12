from __future__ import annotations

from pathlib import Path
import json
import unittest
from unittest.mock import patch

from app.adapters.smartrecruiters import SmartRecruitersAdapter
from app.config import load_company_config


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "smartrecruiters"


class SmartRecruitersAdapterTest(unittest.TestCase):
    def test_normalizes_grab_fixture(self) -> None:
        company = load_company_config("Grab")
        adapter = SmartRecruitersAdapter()
        result = adapter.fetch_from_file(
            company.source_key,
            str(FIXTURE_DIR / "grab_jobs.json"),
        )

        health = adapter.health_check(result)
        postings = adapter.normalize(result, company)

        self.assertEqual(health.status, "healthy")
        self.assertEqual(health.fetched_count, 2)
        self.assertEqual(postings[0].source_job_id, "744000121979117")
        self.assertEqual(postings[0].department, "Strategy & Planning")
        self.assertEqual(postings[0].locations, ["Singapore, Singapore"])
        self.assertEqual(postings[0].employment_type, "Full-time")
        self.assertIn("cross-functional strategy", postings[0].description_text)
        self.assertEqual(postings[0].source_type, "smartrecruiters")
        self.assertTrue(postings[0].source_url.startswith("https://jobs.smartrecruiters.com/"))
        self.assertEqual(postings[1].department, "Group MD&A")
        self.assertEqual(postings[1].locations, ["Phnom Penh, kh"])

    def test_zero_job_response_is_healthy(self) -> None:
        company = load_company_config("Grab")
        adapter = SmartRecruitersAdapter()
        result = adapter.fetch_from_file(
            company.source_key,
            str(FIXTURE_DIR / "zero_jobs.json"),
        )

        self.assertEqual(adapter.health_check(result).status, "healthy")
        self.assertEqual(adapter.normalize(result, company), [])

    def test_incomplete_payload_fails_loudly(self) -> None:
        company = load_company_config("Grab")
        adapter = SmartRecruitersAdapter()
        result = adapter.fetch_from_file(
            company.source_key,
            str(FIXTURE_DIR / "malformed_jobs.json"),
        )

        health = adapter.health_check(result)

        self.assertEqual(health.status, "failing")
        self.assertIn("postings array", health.error_summary or "")
        with self.assertRaises(ValueError):
            adapter.normalize(result, company)

    def test_fetch_paginates_and_requires_every_detail(self) -> None:
        details = json.loads((FIXTURE_DIR / "grab_jobs.json").read_text(encoding="utf-8"))[
            "postings"
        ]
        adapter = SmartRecruitersAdapter(detail_workers=2)
        adapter.page_size = 1

        def open_url(request, timeout):
            del timeout
            url = request.full_url
            if "offset=0" in url:
                return _FakeResponse({"totalFound": 2, "content": [{"id": details[0]["id"]}]})
            if "offset=1" in url:
                return _FakeResponse({"totalFound": 2, "content": [{"id": details[1]["id"]}]})
            for detail in details:
                if url.endswith(f"/{detail['id']}"):
                    return _FakeResponse(detail)
            raise AssertionError(f"unexpected URL: {url}")

        with patch("urllib.request.urlopen", side_effect=open_url):
            result = adapter.fetch("Grab")

        self.assertEqual(result.status, "success")
        self.assertEqual(adapter.health_check(result).fetched_count, 2)
        self.assertEqual(
            [posting["id"] for posting in json.loads(result.response_body)["postings"]],
            [details[0]["id"], details[1]["id"]],
        )

    def test_detail_failure_fails_the_whole_source_loudly(self) -> None:
        adapter = SmartRecruitersAdapter(detail_workers=1)

        def open_url(request, timeout):
            del timeout
            if "?limit=" in request.full_url:
                return _FakeResponse({"totalFound": 1, "content": [{"id": "posting-1"}]})
            raise TimeoutError("detail timed out")

        with patch("urllib.request.urlopen", side_effect=open_url):
            result = adapter.fetch("Grab")

        self.assertEqual(result.status, "failure")
        health = adapter.health_check(result)
        self.assertEqual(health.status, "failing")
        self.assertIn("detail timed out", health.error_summary or "")


class _FakeResponse:
    status = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self) -> bytes:
        return self.body


if __name__ == "__main__":
    unittest.main()
