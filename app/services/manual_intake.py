"""Manual URL/text intake for roles outside configured ATS adapters."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.adapters.utils import clean_html, compact_text, normal_key
from app.config import DEFAULT_DB_PATH
from app.db import (
    connect,
    get_postings_by_ids,
    init_db,
    persist_evaluation,
    upsert_company,
    upsert_postings,
    upsert_source,
)
from app.models import CompanyConfig, JobPosting, utc_now
from app.services.evaluate import evaluate_role, input_hash


MIN_EXTRACTED_TEXT_LENGTH = 120


class ManualExtractionError(RuntimeError):
    """Raised when a URL cannot be turned into usable job-description text."""


@dataclass(frozen=True)
class ManualIntakeResult:
    status: str
    job_id: int | None
    evaluated_count: int
    message: str


@dataclass(frozen=True)
class ManualPostingMetadata:
    company: str
    title: str
    locations: list[str]
    department: str | None
    employment_type: str | None


def add_text_intake(
    text: str,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    source_url: str | None = None,
) -> ManualIntakeResult:
    cleaned_text = compact_text(text)
    if not cleaned_text:
        raise ValueError("manual job-description text cannot be empty")

    metadata = _metadata_from_text(text)
    company = _company_from_metadata(metadata, source_url)
    posting = _posting_from_text(cleaned_text, metadata, source_url)

    conn = connect(db_path)
    init_db(conn)
    company_id = upsert_company(conn, company)
    source_id = upsert_source(conn, company_id, company)
    seen_at = utc_now()
    upsert_result = upsert_postings(conn, company_id, source_id, [posting], seen_at)
    candidate_ids = upsert_result.new_posting_ids + upsert_result.changed_posting_ids
    job_id = _job_id_for_source_job_id(conn, source_id, posting.source_job_id)

    evaluated_count = 0
    for row in get_postings_by_ids(conn, candidate_ids):
        if persist_evaluation(conn, int(row["id"]), input_hash(row), evaluate_role(row, company)):
            evaluated_count += 1

    conn.commit()
    return ManualIntakeResult(
        status="stored",
        job_id=job_id,
        evaluated_count=evaluated_count,
        message=f"Stored manual role {job_id}: {metadata.company} - {metadata.title}",
    )


def add_url_intake(
    url: str,
    *,
    db_path: Path = DEFAULT_DB_PATH,
) -> ManualIntakeResult:
    _validate_http_url(url)
    conn = connect(db_path)
    init_db(conn)
    try:
        text = fetch_url_text(url)
    except ManualExtractionError as exc:
        _record_manual_request(conn, url, str(exc))
        conn.commit()
        return ManualIntakeResult(
            status="needs_text",
            job_id=None,
            evaluated_count=0,
            message=(
                "Could not extract a usable job description from the URL. "
                f"URL preserved; paste the JD with: job-agent add-text - --url {url}"
            ),
        )
    finally:
        conn.close()

    return add_text_intake(text, db_path=db_path, source_url=url)


def fetch_url_text(url: str) -> str:
    try:
        response = httpx.get(url, timeout=15, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ManualExtractionError(f"url_fetch_failed: {exc}") from exc

    extracted = clean_html(response.text)
    if len(extracted) < MIN_EXTRACTED_TEXT_LENGTH:
        raise ManualExtractionError("url_extraction_too_short")
    return extracted


def _validate_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("add-url only supports http(s) URLs")


def read_text_input(path_or_dash: str) -> str:
    if path_or_dash == "-":
        import sys

        return sys.stdin.read()
    return Path(path_or_dash).read_text(encoding="utf-8")


def _metadata_from_text(text: str) -> ManualPostingMetadata:
    title = _field_value(text, "title") or _first_content_line(text) or "Manual role"
    company = _field_value(text, "company") or "Manual Intake"
    locations = _locations_from_text(text)
    return ManualPostingMetadata(
        company=company,
        title=title,
        locations=locations,
        department=_field_value(text, "department") or _field_value(text, "team"),
        employment_type=_field_value(text, "employment type")
        or _field_value(text, "commitment"),
    )


def _posting_from_text(
    text: str,
    metadata: ManualPostingMetadata,
    source_url: str | None,
) -> JobPosting:
    payload_hash = hashlib.sha256(f"{source_url or ''}\n{text}".encode("utf-8")).hexdigest()
    source_job_id = payload_hash[:24]
    return JobPosting(
        company=metadata.company,
        title=metadata.title,
        locations=metadata.locations,
        department=metadata.department,
        employment_type=metadata.employment_type,
        description_text=text,
        source_type="manual",
        source_url=source_url or "manual:text",
        source_job_id=source_job_id,
        source_posted_at=None,
        raw_payload_hash=payload_hash,
        canonical_key="-".join(
            part
            for part in (
                normal_key(metadata.company),
                normal_key(metadata.title),
                source_job_id[:12],
            )
            if part
        ),
    )


def _company_from_metadata(
    metadata: ManualPostingMetadata,
    source_url: str | None,
) -> CompanyConfig:
    return CompanyConfig(
        name=metadata.company,
        tier=3,
        enabled=True,
        ats_type="manual",
        source_key=normal_key(metadata.company) or "manual-intake",
        careers_url=source_url or "manual:text",
        target_locations=metadata.locations,
        target_role_family_notes="Manual intake role selected by the owner.",
        warm_path=False,
    )


def _field_value(text: str, field: str) -> str | None:
    pattern = re.compile(rf"^\s*{re.escape(field)}\s*:\s*(.+?)\s*$", flags=re.IGNORECASE)
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            return compact_text(match.group(1))
    return None


def _locations_from_text(text: str) -> list[str]:
    raw_locations = _field_value(text, "location") or _field_value(text, "locations")
    if not raw_locations:
        return ["Manual / Unknown"]
    locations = [compact_text(part) for part in re.split(r"\s*[;|]\s*", raw_locations)]
    return [location for location in locations if location] or ["Manual / Unknown"]


def _first_content_line(text: str) -> str | None:
    for line in text.splitlines():
        cleaned = compact_text(line)
        if cleaned:
            return cleaned[:140]
    return None


def _job_id_for_source_job_id(
    conn: sqlite3.Connection,
    source_id: int,
    source_job_id: str,
) -> int:
    row = conn.execute(
        """
        SELECT id
        FROM job_postings
        WHERE source_id = ? AND source_job_id = ?
        """,
        (source_id, source_job_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("manual intake stored no posting")
    return int(row["id"])


def _record_manual_request(
    conn: sqlite3.Connection,
    url: str,
    error_summary: str,
) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO manual_intake_requests (url, status, error_summary, created_at, updated_at)
        VALUES (?, 'needs_text', ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
          status = 'needs_text',
          error_summary = excluded.error_summary,
          updated_at = excluded.updated_at
        """,
        (url, error_summary, now, now),
    )
