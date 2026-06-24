"""Greenhouse public job board adapter."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from typing import Any

from app.adapters.utils import clean_html, normal_key
from app.models import CompanyConfig, FetchResult, JobPosting, SourceHealth


class GreenhouseAdapter:
    """Adapter for `boards-api.greenhouse.io/v1/boards/{token}/jobs`."""

    source_type = "greenhouse"
    parser_version = "greenhouse_v1"

    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def endpoint(self, source_key: str) -> str:
        return f"https://boards-api.greenhouse.io/v1/boards/{source_key}/jobs?content=true"

    def fetch(self, source_key: str) -> FetchResult:
        url = self.endpoint(source_key)
        start = time.monotonic()
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "job-search-agent-checkpoint-b/0.1"},
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
        return str(raw_job["id"])

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
        department = _first_name(job.get("departments"))
        locations = _locations(job)
        raw = json.dumps(job, sort_keys=True)
        raw_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        requisition_id = str(
            job.get("requisition_id") or job.get("internal_job_id") or source_job_id
        )
        canonical_key = normal_key(
            "|".join([company.name, title, department or "", requisition_id])
        )

        return JobPosting(
            company=company.name,
            title=title,
            locations=locations,
            department=department,
            employment_type=None,
            description_text=clean_html(job.get("content")),
            source_type=self.source_type,
            source_url=str(job.get("absolute_url") or ""),
            source_job_id=source_job_id,
            source_posted_at=job.get("first_published") or job.get("updated_at"),
            raw_payload_hash=raw_hash,
            canonical_key=canonical_key,
        )


def _first_name(items: object) -> str | None:
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict) and first.get("name"):
            return str(first["name"])
    return None


def _locations(job: dict[str, Any]) -> list[str]:
    values: list[str] = []
    location = job.get("location")
    if isinstance(location, dict) and location.get("name"):
        values.append(str(location["name"]))
    for office in job.get("offices") or []:
        if isinstance(office, dict) and office.get("name"):
            name = str(office["name"])
            if name not in values:
                values.append(name)
    return values
