"""SmartRecruiters public Posting API adapter."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import time
import urllib.error
import urllib.request
from typing import Any

from app.adapters.utils import clean_html, compact_text, normal_key
from app.models import CompanyConfig, FetchResult, JobPosting, SourceHealth


class SmartRecruitersAdapter:
    """Adapter for `api.smartrecruiters.com/v1/companies/{company}/postings`."""

    source_type = "smartrecruiters"
    parser_version = "smartrecruiters_v1"
    page_size = 100

    def __init__(self, timeout_seconds: int = 20, detail_workers: int = 8) -> None:
        self.timeout_seconds = timeout_seconds
        self.detail_workers = detail_workers

    def endpoint(self, source_key: str) -> str:
        return self._page_endpoint(source_key, offset=0)

    def fetch(self, source_key: str) -> FetchResult:
        url = self.endpoint(source_key)
        start = time.monotonic()
        try:
            summaries, total_found = self._fetch_summaries(source_key)
            details = self._fetch_details(source_key, summaries)
            body = json.dumps(
                {"totalFound": total_found, "postings": details},
                sort_keys=True,
            )
            return FetchResult(
                source_type=self.source_type,
                source_key=source_key,
                url=url,
                status="success",
                http_status=200,
                duration_ms=int((time.monotonic() - start) * 1000),
                response_body=body,
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return self._failure_result(
                source_key,
                url,
                start,
                body=body,
                http_status=exc.code,
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - connector failures must be persisted loudly.
            return self._failure_result(
                source_key,
                url,
                start,
                body="",
                http_status=None,
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
            raise ValueError("SmartRecruiters job missing id")
        return str(source_job_id)

    def health_check(self, result: FetchResult) -> SourceHealth:
        if result.status != "success":
            return SourceHealth("failing", 0, result.error or "fetch failed")
        try:
            payload = json.loads(result.response_body)
        except json.JSONDecodeError as exc:
            return SourceHealth("failing", 0, f"malformed JSON: {exc}")
        if not isinstance(payload, dict):
            return SourceHealth("failing", 0, "payload is not an object")
        postings = payload.get("postings")
        total_found = payload.get("totalFound")
        if not isinstance(postings, list):
            return SourceHealth("failing", 0, "payload missing postings array")
        if not isinstance(total_found, int) or total_found != len(postings):
            return SourceHealth("failing", 0, "payload posting count is incomplete")
        if any(not isinstance(posting, dict) or not posting.get("id") for posting in postings):
            return SourceHealth("failing", 0, "postings array contains invalid posting")
        return SourceHealth("healthy", len(postings))

    def normalize(self, result: FetchResult, company: CompanyConfig) -> list[JobPosting]:
        health = self.health_check(result)
        if health.status != "healthy":
            raise ValueError(health.error_summary or "source is not healthy")
        payload = json.loads(result.response_body)
        return [self._normalize_job(posting, company) for posting in payload["postings"]]

    def _fetch_summaries(self, source_key: str) -> tuple[list[dict[str, Any]], int]:
        summaries: list[dict[str, Any]] = []
        offset = 0
        total_found: int | None = None
        while total_found is None or offset < total_found:
            payload = self._read_json(self._page_endpoint(source_key, offset))
            content = payload.get("content")
            page_total = payload.get("totalFound")
            if not isinstance(content, list) or not isinstance(page_total, int):
                raise ValueError("SmartRecruiters list payload missing content/totalFound")
            if any(not isinstance(item, dict) or not item.get("id") for item in content):
                raise ValueError("SmartRecruiters list contains invalid posting")
            if total_found is None:
                total_found = page_total
            elif total_found != page_total:
                raise ValueError("SmartRecruiters totalFound changed during pagination")
            summaries.extend(content)
            if not content and offset < total_found:
                raise ValueError("SmartRecruiters pagination ended before totalFound")
            offset += len(content)
        return summaries, total_found or 0

    def _fetch_details(
        self,
        source_key: str,
        summaries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not summaries:
            return []
        details: list[dict[str, Any] | None] = [None] * len(summaries)
        with ThreadPoolExecutor(max_workers=self.detail_workers) as executor:
            futures = {
                executor.submit(
                    self._read_json,
                    self._detail_endpoint(source_key, str(summary["id"])),
                ): index
                for index, summary in enumerate(summaries)
            }
            for future in as_completed(futures):
                index = futures[future]
                detail = future.result()
                if not detail.get("id"):
                    raise ValueError("SmartRecruiters detail missing posting id")
                details[index] = detail
        if any(detail is None for detail in details):
            raise ValueError("SmartRecruiters detail fetch was incomplete")
        return [detail for detail in details if detail is not None]

    def _read_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 job-search-agent/0.1"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body = response.read().decode("utf-8")
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("SmartRecruiters response is not an object")
        return payload

    def _page_endpoint(self, source_key: str, offset: int) -> str:
        return (
            f"https://api.smartrecruiters.com/v1/companies/{source_key}/postings"
            f"?limit={self.page_size}&offset={offset}"
        )

    def _detail_endpoint(self, source_key: str, posting_id: str) -> str:
        return (
            f"https://api.smartrecruiters.com/v1/companies/{source_key}/postings/{posting_id}"
        )

    def _failure_result(
        self,
        source_key: str,
        url: str,
        start: float,
        *,
        body: str,
        http_status: int | None,
        error: str,
    ) -> FetchResult:
        return FetchResult(
            source_type=self.source_type,
            source_key=source_key,
            url=url,
            status="failure",
            http_status=http_status,
            duration_ms=int((time.monotonic() - start) * 1000),
            response_body=body,
            error=error,
        )

    def _normalize_job(
        self,
        posting: dict[str, Any],
        company: CompanyConfig,
    ) -> JobPosting:
        source_job_id = self.identity(posting)
        title = compact_text(str(posting.get("name") or ""))
        department = _label(posting.get("department")) or _custom_department(posting)
        if not department:
            department = _label(posting.get("function"))
        raw = json.dumps(posting, sort_keys=True)
        raw_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        canonical_key = normal_key(
            "|".join(
                [
                    company.name,
                    title,
                    department or "",
                    str(posting.get("refNumber") or source_job_id),
                ]
            )
        )
        return JobPosting(
            company=company.name,
            title=title,
            locations=_locations(posting),
            department=department,
            employment_type=_label(posting.get("typeOfEmployment")),
            description_text=_description(posting),
            source_type=self.source_type,
            source_url=str(posting.get("postingUrl") or posting.get("applyUrl") or ""),
            source_job_id=source_job_id,
            source_posted_at=_optional_str(posting.get("releasedDate")),
            raw_payload_hash=raw_hash,
            canonical_key=canonical_key,
        )


def _label(value: object) -> str | None:
    if isinstance(value, dict):
        return _optional_str(value.get("label"))
    return None


def _custom_department(posting: dict[str, Any]) -> str | None:
    for field in posting.get("customField") or []:
        if not isinstance(field, dict):
            continue
        if str(field.get("fieldLabel") or "").lower() in {"department", "department name"}:
            return _optional_str(field.get("valueLabel"))
    return None


def _locations(posting: dict[str, Any]) -> list[str]:
    location = posting.get("location")
    if not isinstance(location, dict):
        return []
    full = _optional_str(location.get("fullLocation"))
    if full:
        return [full]
    parts = [location.get("city"), location.get("region"), location.get("country")]
    rendered = ", ".join(str(part) for part in parts if part)
    return [rendered] if rendered else []


def _description(posting: dict[str, Any]) -> str:
    job_ad = posting.get("jobAd")
    if not isinstance(job_ad, dict):
        return ""
    sections = job_ad.get("sections")
    if not isinstance(sections, dict):
        return ""
    values: list[str] = []
    for section in sections.values():
        if not isinstance(section, dict):
            continue
        text = clean_html(_optional_str(section.get("text")))
        if text:
            values.append(text)
    return compact_text("\n\n".join(values))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
