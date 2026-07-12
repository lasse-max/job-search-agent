"""Manual URL/text intake for roles outside configured ATS adapters."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.adapters.utils import clean_html, compact_text, normal_key
from app.config import DEFAULT_DB_PATH
from app.db import (
    connect_runtime_database,
    get_postings_by_ids,
    init_db,
    persist_evaluation,
    upsert_company,
    upsert_postings,
    upsert_source,
)
from app.models import CompanyConfig, JobPosting, utc_now
from app.services.evaluate import HYBRID_EVALUATOR_VERSION, evaluate_role, input_hash


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


@dataclass(frozen=True)
class ManualIntakeQueueSummary:
    processed: int
    completed: int
    needs_text: int
    failed: int
    skipped_schema: bool = False


def add_text_intake(
    text: str,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    database_url: str | None = None,
    source_url: str | None = None,
) -> ManualIntakeResult:
    cleaned_text = compact_text(text)
    if not cleaned_text:
        raise ValueError("manual job-description text cannot be empty")

    metadata = _metadata_from_text(text)
    company = _company_from_metadata(metadata, source_url)
    posting = _posting_from_text(cleaned_text, metadata, source_url)

    conn = connect_runtime_database(db_path, database_url=database_url)
    try:
        init_db(conn)
        company_id = _manual_company_id(conn, company)
        source_id = upsert_source(conn, company_id, company)
        seen_at = utc_now()
        upsert_result = upsert_postings(conn, company_id, source_id, [posting], seen_at)
        candidate_ids = upsert_result.new_posting_ids + upsert_result.changed_posting_ids
        job_id = _job_id_for_source_job_id(conn, source_id, posting.source_job_id)

        evaluated_count = 0
        for row in get_postings_by_ids(conn, candidate_ids):
            evaluation = evaluate_role(row, company)
            if persist_evaluation(conn, int(row["id"]), input_hash(row), evaluation):
                evaluated_count += 1
        conn.commit()
    finally:
        conn.close()
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
    database_url: str | None = None,
) -> ManualIntakeResult:
    _validate_http_url(url)
    conn = connect_runtime_database(db_path, database_url=database_url)
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

    return add_text_intake(
        text,
        db_path=db_path,
        database_url=database_url,
        source_url=url,
    )


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


def process_manual_intake_queue(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    database_url: str | None = None,
    limit: int = 10,
) -> ManualIntakeQueueSummary:
    if limit <= 0:
        return ManualIntakeQueueSummary(0, 0, 0, 0)
    conn = connect_runtime_database(db_path, database_url=database_url)
    init_db(conn)
    try:
        submissions = conn.execute(
            """
            SELECT * FROM manual_intake_submissions
            WHERE status = 'queued'
            ORDER BY created_at, id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except Exception as exc:  # noqa: BLE001 - migration may not be applied yet.
        conn.close()
        if _missing_queue_table(exc):
            return ManualIntakeQueueSummary(0, 0, 0, 0, skipped_schema=True)
        raise

    completed = 0
    needs_text = 0
    failed = 0
    for submission in submissions:
        submission_id = int(submission["id"])
        claimed = conn.execute(
            """
            UPDATE manual_intake_submissions
            SET status = 'processing', updated_at = ?
            WHERE id = ? AND status = 'queued'
            """,
            (utc_now(), submission_id),
        )
        conn.commit()
        if claimed.rowcount <= 0:
            continue
        try:
            source_url = str(submission["source_url"] or "") or None
            if submission["intake_mode"] == "url":
                try:
                    jd_text = fetch_url_text(str(source_url))
                except ManualExtractionError as exc:
                    _update_submission(
                        conn,
                        submission_id,
                        status="needs_text",
                        error_summary=str(exc),
                    )
                    needs_text += 1
                    continue
            else:
                jd_text = str(submission["jd_text"] or "")
            enriched_text = _enriched_submission_text(submission, jd_text)
            result = add_text_intake(
                enriched_text,
                db_path=db_path,
                database_url=database_url,
                source_url=source_url,
            )
            if result.job_id is None:
                raise RuntimeError("manual intake stored no posting")
            _apply_submission_destination(
                conn,
                result.job_id,
                str(submission["destination"]),
                str(submission["note"] or ""),
            )
            _update_submission(
                conn,
                submission_id,
                status="completed",
                job_posting_id=result.job_id,
            )
            completed += 1
        except Exception as exc:  # noqa: BLE001 - isolate one owner submission.
            _update_submission(
                conn,
                submission_id,
                status="failed",
                error_summary=f"{type(exc).__name__}: {exc}",
            )
            failed += 1
    conn.close()
    return ManualIntakeQueueSummary(
        processed=completed + needs_text + failed,
        completed=completed,
        needs_text=needs_text,
        failed=failed,
    )


def _enriched_submission_text(submission: Any, jd_text: str) -> str:
    headers = [
        f"Company: {submission['company']}",
        f"Title: {submission['title']}",
    ]
    if submission["location"]:
        headers.append(f"Location: {submission['location']}")
    return "\n".join(headers) + "\n\n" + jd_text


def _apply_submission_destination(
    conn: Any,
    job_id: int,
    destination: str,
    note: str,
) -> None:
    row = _current_manual_evaluation_row(conn, job_id)
    if destination == "potential_matches":
        return
    if destination == "to_apply":
        conn.execute(
            """
            UPDATE opportunity_reviews
            SET state = 'interested', decision_reason = ?, reviewed_at = ?, snooze_until = NULL
            WHERE job_posting_id = ?
            """,
            (note or None, utc_now(), job_id),
        )
        conn.commit()
        return
    if destination != "applied":
        raise ValueError(f"unsupported manual intake destination: {destination}")

    evaluated = json.loads(row["evaluation_json"])
    locations = json.loads(row["locations_json"] or "[]")
    applied_at = utc_now()
    calendar_week = datetime.fromisoformat(applied_at).isocalendar().week
    snapshot = {
        "captured_at": applied_at,
        "role_evaluation_id": row["evaluation_id"],
        "model_version": row["model_version"],
        "evaluated_at": row["evaluated_at"],
        "evaluation": evaluated,
    }
    conn.execute(
        """
        INSERT INTO applications (
          company, role, location, url, stage, applied_at, applied_calendar_week,
          notes, source_posting_id, eval_snapshot_json
        ) VALUES (?, ?, ?, ?, 'applied', ?, ?, ?, ?, ?)
        ON CONFLICT(source_posting_id) DO NOTHING
        """,
        (
            row["company"],
            row["title"],
            " · ".join(str(value) for value in locations) or "Location not listed",
            row["source_url"],
            applied_at,
            calendar_week,
            note or None,
            job_id,
            json.dumps(snapshot, sort_keys=True),
        ),
    )
    conn.commit()


def _current_manual_evaluation_row(conn: Any, job_id: int) -> Any:
    row = conn.execute(
        """
        SELECT jp.*, c.name AS company, re.id AS evaluation_id,
               re.model_version, re.evaluation_json, re.created_at AS evaluated_at
        FROM job_postings jp
        JOIN companies c ON c.id = jp.company_id
        JOIN role_evaluations re ON re.id = (
          SELECT MAX(latest.id) FROM role_evaluations latest
          WHERE latest.job_posting_id = jp.id
        )
        WHERE jp.id = ?
        """,
        (job_id,),
    ).fetchone()
    if row is None or not str(row["model_version"]).endswith(f"|{HYBRID_EVALUATOR_VERSION}"):
        raise RuntimeError("manual evaluation is not current and calibrated")
    evaluated = json.loads(row["evaluation_json"])
    provenance = evaluated.get("provenance") or {}
    if "deterministic_fallback" in str(row["model_version"]) or any(
        str(provenance.get(key, "")).lower() == "true"
        for key in ("is_fallback", "fallback_quality")
    ):
        raise RuntimeError("manual evaluation fallback cannot enter the scored pipeline")
    return row


def _update_submission(
    conn: Any,
    submission_id: int,
    *,
    status: str,
    job_posting_id: int | None = None,
    error_summary: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE manual_intake_submissions
        SET status = ?, job_posting_id = COALESCE(?, job_posting_id),
            error_summary = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, job_posting_id, error_summary, utc_now(), submission_id),
    )
    conn.commit()


def _missing_queue_table(exc: Exception) -> bool:
    message = str(exc).lower()
    return "manual_intake_submissions" in message and (
        "does not exist" in message or "no such table" in message
    )


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


def _manual_company_id(conn: Any, company: CompanyConfig) -> int:
    existing = conn.execute(
        "SELECT id FROM companies WHERE name = ?",
        (company.name,),
    ).fetchone()
    if existing is not None:
        return int(existing["id"])
    return upsert_company(conn, company)


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
