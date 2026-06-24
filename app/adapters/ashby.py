"""Ashby public job-board adapter."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from typing import Any

from app.adapters.utils import clean_html, compact_text, normal_key
from app.models import CompanyConfig, FetchResult, JobPosting, SourceHealth


class AshbyAdapter:
    """Adapter for `api.ashbyhq.com/posting-api/job-board/{org}`."""

    source_type = "ashby"
    parser_version = "ashby_v1"

    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def endpoint(self, source_key: str) -> str:
        return (
            f"https://api.ashbyhq.com/posting-api/job-board/{source_key}"
            "?includeCompensation=false"
        )

    def fetch(self, source_key: str) -> FetchResult:
        url = self.endpoint(source_key)
        start = time.monotonic()
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 job-search-agent/0.1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                return FetchResult(
                    source_type=self.source_type,
                    source_key=source_key,
                    url=url,
                    status="success",
                    http_status=response.status,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    response_body=body,
                )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return FetchResult(
                source_type=self.source_type,
                source_key=source_key,
                url=url,
                status="failure",
                http_status=exc.code,
                duration_ms=int((time.monotonic() - start) * 1000),
                response_body=body,
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - record connector failure loudly.
            return FetchResult(
                source_type=self.source_type,
                source_key=source_key,
                url=url,
                status="failure",
                http_status=None,
                duration_ms=int((time.monotonic() - start) * 1000),
                response_body="",
                error=f"{type(exc).__name__}: {exc}",
            )

    def fetch_from_file(self, source_key: str, fixture_path: str) -> FetchResult:
        with open(fixture_path, encoding="utf-8") as handle:
            body = handle.read()
        return FetchResult(
            source_type=self.source_type,
            source_key=source_key,
            url=f"fixture://{fixture_path}",
            status="success",
            http_status=200,
            duration_ms=0,
            response_body=body,
        )

    def identity(self, raw_job: dict[str, Any]) -> str:
        source_job_id = raw_job.get("id")
        if not source_job_id:
            raise ValueError("Ashby job missing id")
        return str(source_job_id)

    def health_check(self, result: FetchResult) -> SourceHealth:
        if result.status != "success":
            return SourceHealth("failing", 0, result.error or "fetch failed")
        try:
            payload = json.loads(result.response_body)
        except json.JSONDecodeError as exc:
            return SourceHealth("failing", 0, f"malformed JSON: {exc}")
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            return SourceHealth("failing", 0, "payload missing jobs array")
        if any(not isinstance(job, dict) or not job.get("id") for job in jobs):
            return SourceHealth("failing", 0, "jobs array contains invalid posting")
        return SourceHealth("healthy", len(jobs))

    def normalize(self, result: FetchResult, company: CompanyConfig) -> list[JobPosting]:
        health = self.health_check(result)
        if health.status != "healthy":
            raise ValueError(health.error_summary or "source is not healthy")

        payload = json.loads(result.response_body)
        postings: list[JobPosting] = []
        for job in payload["jobs"]:
            postings.append(self._normalize_job(job, company))
        return postings

    def _normalize_job(self, job: dict[str, Any], company: CompanyConfig) -> JobPosting:
        source_job_id = self.identity(job)
        title = str(job.get("title") or "").strip()
        department = _department(job)
        locations = _locations(job)
        raw = json.dumps(job, sort_keys=True)
        raw_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        canonical_key = normal_key(
            "|".join([company.name, title, department or "", source_job_id])
        )

        return JobPosting(
            company=company.name,
            title=title,
            locations=locations,
            department=department,
            employment_type=_optional_str(job.get("employmentType")),
            description_text=_description(job),
            source_type=self.source_type,
            source_url=str(job.get("jobUrl") or job.get("applyUrl") or ""),
            source_job_id=source_job_id,
            source_posted_at=_optional_str(job.get("publishedAt")),
            raw_payload_hash=raw_hash,
            canonical_key=canonical_key,
        )


def _department(job: dict[str, Any]) -> str | None:
    return _optional_str(job.get("department") or job.get("team"))


def _description(job: dict[str, Any]) -> str:
    plain = _optional_str(job.get("descriptionPlain"))
    if plain:
        return compact_text(plain)
    return clean_html(_optional_str(job.get("descriptionHtml")))


def _locations(job: dict[str, Any]) -> list[str]:
    values: list[str] = []
    _append_location(values, job.get("location"))
    for secondary in job.get("secondaryLocations") or []:
        if isinstance(secondary, dict):
            _append_location(values, secondary.get("location"))
    if not values:
        _append_location(values, _postal_location(job.get("address")))
    return values


def _append_location(values: list[str], value: object) -> None:
    if not value:
        return
    location = str(value).strip()
    if location and location not in values:
        values.append(location)


def _postal_location(address: object) -> str | None:
    if not isinstance(address, dict):
        return None
    postal = address.get("postalAddress")
    if not isinstance(postal, dict):
        return None
    parts = [
        postal.get("addressLocality"),
        postal.get("addressRegion"),
        postal.get("addressCountry"),
    ]
    return ", ".join(str(part) for part in parts if part)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
