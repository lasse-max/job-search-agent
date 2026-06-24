"""Lever public postings adapter."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

from app.adapters.utils import clean_html, compact_text, normal_key
from app.models import CompanyConfig, FetchResult, JobPosting, SourceHealth


class LeverAdapter:
    """Adapter for `api.lever.co/v0/postings/{company}?mode=json`."""

    source_type = "lever"
    parser_version = "lever_v1"

    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def endpoint(self, source_key: str) -> str:
        return f"https://api.lever.co/v0/postings/{source_key}?mode=json"

    def fetch(self, source_key: str) -> FetchResult:
        url = self.endpoint(source_key)
        start = time.monotonic()
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "job-search-agent-stage1/0.1"},
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
            raise ValueError("Lever posting missing id")
        return str(source_job_id)

    def health_check(self, result: FetchResult) -> SourceHealth:
        if result.status != "success":
            return SourceHealth("failing", 0, result.error or "fetch failed")
        try:
            payload = json.loads(result.response_body)
        except json.JSONDecodeError as exc:
            return SourceHealth("failing", 0, f"malformed JSON: {exc}")
        if not isinstance(payload, list):
            return SourceHealth("failing", 0, "payload is not a postings array")
        if any(not isinstance(job, dict) or not job.get("id") for job in payload):
            return SourceHealth("failing", 0, "postings array contains invalid posting")
        return SourceHealth("healthy", len(payload))

    def normalize(self, result: FetchResult, company: CompanyConfig) -> list[JobPosting]:
        health = self.health_check(result)
        if health.status != "healthy":
            raise ValueError(health.error_summary or "source is not healthy")

        payload = json.loads(result.response_body)
        postings: list[JobPosting] = []
        for job in payload:
            postings.append(self._normalize_job(job, company))
        return postings

    def _normalize_job(self, job: dict[str, Any], company: CompanyConfig) -> JobPosting:
        source_job_id = self.identity(job)
        title = str(job.get("text") or "").strip()
        categories = job.get("categories") if isinstance(job.get("categories"), dict) else {}
        department = _optional_str(categories.get("team"))
        locations = _locations(categories)
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
            employment_type=_optional_str(categories.get("commitment")),
            description_text=_description(job),
            source_type=self.source_type,
            source_url=str(job.get("hostedUrl") or job.get("applyUrl") or ""),
            source_job_id=source_job_id,
            source_posted_at=_created_at(job.get("createdAt")),
            raw_payload_hash=raw_hash,
            canonical_key=canonical_key,
        )


def _description(job: dict[str, Any]) -> str:
    plain = _optional_str(
        job.get("descriptionPlain")
        or job.get("descriptionBodyPlain")
        or job.get("additionalPlain")
        or job.get("openingPlain")
    )
    if plain:
        return compact_text(plain)
    return clean_html(
        _optional_str(
            job.get("description") or job.get("descriptionBody") or job.get("additional")
        )
    )


def _locations(categories: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for location in categories.get("allLocations") or []:
        _append_location(values, location)
    _append_location(values, categories.get("location"))
    return values


def _append_location(values: list[str], value: object) -> None:
    if not value:
        return
    location = str(value).strip()
    if location and location not in values:
        values.append(location)


def _created_at(value: object) -> str | None:
    if value is None:
        return None
    try:
        timestamp_ms = int(value)
    except (TypeError, ValueError):
        return str(value)
    return datetime.fromtimestamp(timestamp_ms / 1000, UTC).replace(microsecond=0).isoformat()


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
