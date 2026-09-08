import unittest
from unittest.mock import patch

import httpx

from app.services.manual_intake import (
    MAX_JOB_TEXT_LENGTH, ManualExtractionError, fetch_url_text,
)


class ManualPageExtractionTest(unittest.TestCase):
    def fetch(self, page: str) -> str:
        response = httpx.Response(200, text=page)
        response.request = httpx.Request("GET", "https://example.com/job")
        with patch("app.services.manual_intake.httpx.get", return_value=response):
            return fetch_url_text("https://example.com/job")

    def test_scripts_and_styles_cannot_swamp_or_pollute_requirements(self) -> None:
        jd = "Lead business strategy and operations. " * 5 + "German fluency is mandatory."
        page = ("<html><head><style>" + "css garbage " * 10000 + "</style></head>"
                "<body><script>" + "page code " * 100000 + "</script><main><h1>Strategy Lead</h1>"
                f"<p>{jd}</p></main><footer>Site footer</footer></body></html>")
        extracted = self.fetch(page)
        self.assertIn("Strategy Lead", extracted)
        self.assertIn(jd, extracted)
        self.assertNotIn("garbage", extracted)
        self.assertNotIn("page code", extracted)
        self.assertNotIn("Site footer", extracted)

    def test_script_only_page_requests_text_instead_of_scoring_code(self) -> None:
        with self.assertRaisesRegex(ManualExtractionError, "too_short"):
            self.fetch("<script>" + "application code " * 500 + "</script><p>Loading</p>")

    def test_oversized_visible_description_is_not_silently_truncated(self) -> None:
        with self.assertRaisesRegex(ManualExtractionError, "job_text_too_long"):
            self.fetch("<p>" + "x" * (MAX_JOB_TEXT_LENGTH + 1) + "</p>")

    def test_invalid_scheme_is_rejected_before_network_access(self) -> None:
        with patch("app.services.manual_intake.httpx.get") as fetch:
            with self.assertRaises(ValueError):
                fetch_url_text("file:///etc/passwd")
        fetch.assert_not_called()
