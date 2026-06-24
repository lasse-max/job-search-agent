"""SQLite persistence for the first discovery vertical slice."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.adapters import parser_version, source_endpoint
from app.config import load_candidate_profile, load_location_policy, load_scoring_policy
from app.models import CompanyConfig, JobPosting, RoleEvaluation, utc_now
from app.services.material import material_hash_for_posting, material_hash_for_row


DEFAULT_EVALUATOR_VERSION = "deterministic_fallback_v1"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  tier INTEGER NOT NULL,
  enabled INTEGER NOT NULL,
  warm_path INTEGER NOT NULL,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS job_sources (
  id INTEGER PRIMARY KEY,
  company_id INTEGER NOT NULL REFERENCES companies(id),
  source_type TEXT NOT NULL,
  source_key TEXT NOT NULL,
  source_url TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  health_status TEXT NOT NULL DEFAULT 'disabled',
  last_success_at TEXT,
  expected_volume_min INTEGER,
  UNIQUE(company_id, source_type, source_key)
);

CREATE TABLE IF NOT EXISTS source_runs (
  id INTEGER PRIMARY KEY,
  job_source_id INTEGER NOT NULL REFERENCES job_sources(id),
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  status TEXT NOT NULL,
  http_status INTEGER,
  fetched_count INTEGER NOT NULL,
  new_count INTEGER NOT NULL,
  changed_count INTEGER NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  error_summary TEXT
);

CREATE TABLE IF NOT EXISTS job_postings (
  id INTEGER PRIMARY KEY,
  company_id INTEGER NOT NULL REFERENCES companies(id),
  source_id INTEGER NOT NULL REFERENCES job_sources(id),
  source_job_id TEXT NOT NULL,
  canonical_key TEXT NOT NULL,
  title TEXT NOT NULL,
  locations_json TEXT NOT NULL,
  department TEXT,
  employment_type TEXT,
  description_text TEXT NOT NULL,
  source_url TEXT NOT NULL,
  posted_at TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  raw_payload_hash TEXT NOT NULL,
  availability_state TEXT NOT NULL,
  missing_successful_scan_count INTEGER NOT NULL DEFAULT 0,
  UNIQUE(source_id, source_job_id)
);

CREATE TABLE IF NOT EXISTS role_evaluations (
  id INTEGER PRIMARY KEY,
  job_posting_id INTEGER NOT NULL REFERENCES job_postings(id),
  profile_version_id TEXT NOT NULL,
  location_policy_version_id TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  model_version TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  evaluation_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(job_posting_id, input_hash, model_version)
);

CREATE TABLE IF NOT EXISTS evaluation_skips (
  id INTEGER PRIMARY KEY,
  job_posting_id INTEGER NOT NULL REFERENCES job_postings(id),
  input_hash TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(job_posting_id, input_hash, reason)
);

CREATE TABLE IF NOT EXISTS opportunity_reviews (
  id INTEGER PRIMARY KEY,
  job_posting_id INTEGER NOT NULL UNIQUE REFERENCES job_postings(id),
  state TEXT NOT NULL,
  decision_reason TEXT,
  reviewed_at TEXT,
  snooze_until TEXT
);

CREATE TABLE IF NOT EXISTS manual_intake_requests (
  id INTEGER PRIMARY KEY,
  url TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL,
  error_summary TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  sent_at TEXT NOT NULL,
  status TEXT NOT NULL,
  error_summary TEXT
);
"""


@dataclass(frozen=True)
class UpsertResult:
    new_posting_ids: list[int]
    changed_posting_ids: list[int]
    unavailable_count: int


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_company(conn: sqlite3.Connection, company: CompanyConfig) -> int:
    conn.execute(
        """
        INSERT INTO companies (name, tier, enabled, warm_path, notes)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
          tier=excluded.tier,
          enabled=excluded.enabled,
          warm_path=excluded.warm_path
        """,
        (company.name, company.tier, int(company.enabled), int(company.warm_path), None),
    )
    return int(
        conn.execute("SELECT id FROM companies WHERE name = ?", (company.name,)).fetchone()["id"]
    )


def upsert_source(
    conn: sqlite3.Connection,
    company_id: int,
    company: CompanyConfig,
    *,
    seed_expected_volume: bool = True,
) -> int:
    source_url = source_endpoint(company.ats_type, company.source_key)
    source_parser_version = parser_version(company.ats_type)
    expected_volume_min = company.expected_volume_min if seed_expected_volume else None
    conn.execute(
        """
        INSERT INTO job_sources (
          company_id, source_type, source_key, source_url, parser_version, health_status,
          expected_volume_min
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_id, source_type, source_key) DO UPDATE SET
          source_url=excluded.source_url,
          parser_version=excluded.parser_version,
          expected_volume_min=COALESCE(job_sources.expected_volume_min, excluded.expected_volume_min)
        """,
        (
            company_id,
            company.ats_type,
            company.source_key,
            source_url,
            source_parser_version,
            "healthy",
            expected_volume_min,
        ),
    )
    return int(
        conn.execute(
            """
            SELECT id FROM job_sources
            WHERE company_id = ? AND source_type = ? AND source_key = ?
            """,
            (company_id, company.ats_type, company.source_key),
        ).fetchone()["id"]
    )


def set_source_health(
    conn: sqlite3.Connection,
    source_id: int,
    health_status: str,
    last_success_at: str | None,
) -> None:
    conn.execute(
        """
        UPDATE job_sources
        SET health_status = ?, last_success_at = COALESCE(?, last_success_at)
        WHERE id = ?
        """,
        (health_status, last_success_at, source_id),
    )


def get_expected_volume_min(conn: sqlite3.Connection, source_id: int) -> int | None:
    row = conn.execute(
        """
        SELECT expected_volume_min
        FROM job_sources
        WHERE id = ?
        """,
        (source_id,),
    ).fetchone()
    if row is None or row["expected_volume_min"] is None:
        return None
    return int(row["expected_volume_min"])


def update_expected_volume_min(
    conn: sqlite3.Connection,
    source_id: int,
    fetched_count: int,
) -> None:
    if fetched_count <= 0:
        return
    learned_minimum = max(1, fetched_count // 5)
    conn.execute(
        """
        UPDATE job_sources
        SET expected_volume_min = MAX(COALESCE(expected_volume_min, 0), ?)
        WHERE id = ?
        """,
        (learned_minimum, source_id),
    )


def recover_expected_volume_min_after_degraded(
    conn: sqlite3.Connection,
    source_id: int,
    *,
    consecutive_runs: int = 3,
) -> None:
    rows = conn.execute(
        """
        SELECT status, fetched_count
        FROM source_runs
        WHERE job_source_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (source_id, consecutive_runs),
    ).fetchall()
    if len(rows) < consecutive_runs:
        return
    if any(row["status"] != "degraded" or int(row["fetched_count"]) <= 0 for row in rows):
        return
    recovered_minimum = max(int(row["fetched_count"]) for row in rows)
    conn.execute(
        """
        UPDATE job_sources
        SET expected_volume_min = ?
        WHERE id = ?
        """,
        (recovered_minimum, source_id),
    )


def upsert_postings(
    conn: sqlite3.Connection,
    company_id: int,
    source_id: int,
    postings: list[JobPosting],
    seen_at: str,
    *,
    count_absences: bool = True,
) -> UpsertResult:
    new_ids: list[int] = []
    changed_ids: list[int] = []
    seen_source_job_ids = {posting.source_job_id for posting in postings}

    for posting in postings:
        existing = conn.execute(
            """
            SELECT *
            FROM job_postings
            WHERE source_id = ? AND source_job_id = ?
            """,
            (source_id, posting.source_job_id),
        ).fetchone()
        values = (
            company_id,
            source_id,
            posting.source_job_id,
            posting.canonical_key,
            posting.title,
            json.dumps(posting.locations),
            posting.department,
            posting.employment_type,
            posting.description_text,
            posting.source_url,
            posting.source_posted_at,
            seen_at,
            seen_at,
            posting.raw_payload_hash,
            posting.availability_state,
        )
        if existing is None:
            cursor = conn.execute(
                """
                INSERT INTO job_postings (
                  company_id, source_id, source_job_id, canonical_key, title, locations_json,
                  department, employment_type, description_text, source_url, posted_at,
                  first_seen_at, last_seen_at, raw_payload_hash, availability_state,
                  missing_successful_scan_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                values,
            )
            job_id = int(cursor.lastrowid)
            new_ids.append(job_id)
            ensure_review(conn, job_id)
            continue

        job_id = int(existing["id"])
        material_changed = material_hash_for_row(existing) != material_hash_for_posting(posting)
        if material_changed:
            conn.execute(
                """
                UPDATE job_postings
                SET company_id = ?, source_id = ?, source_job_id = ?, canonical_key = ?,
                    title = ?, locations_json = ?, department = ?, employment_type = ?,
                    description_text = ?, source_url = ?, posted_at = ?,
                    last_seen_at = ?, raw_payload_hash = ?, availability_state = ?,
                    missing_successful_scan_count = 0
                WHERE id = ?
                """,
                (
                    *values[:11],
                    seen_at,
                    posting.raw_payload_hash,
                    posting.availability_state,
                    job_id,
                ),
            )
            changed_ids.append(job_id)
            resurface_review_on_material_change(conn, job_id)
        else:
            conn.execute(
                """
                UPDATE job_postings
                SET company_id = ?, source_id = ?, source_job_id = ?, canonical_key = ?,
                    title = ?, locations_json = ?, department = ?, employment_type = ?,
                    description_text = ?, source_url = ?, posted_at = ?,
                    last_seen_at = ?, raw_payload_hash = ?, availability_state = 'open',
                    missing_successful_scan_count = 0
                WHERE id = ?
                """,
                (
                    *values[:11],
                    seen_at,
                    posting.raw_payload_hash,
                    job_id,
                ),
            )

    unavailable_count = (
        mark_absences(conn, source_id, seen_source_job_ids) if count_absences else 0
    )
    return UpsertResult(new_ids, changed_ids, unavailable_count)


def mark_absences(
    conn: sqlite3.Connection,
    source_id: int,
    seen_source_job_ids: set[str],
) -> int:
    rows = conn.execute(
        """
        SELECT id, source_job_id, missing_successful_scan_count
        FROM job_postings
        WHERE source_id = ? AND availability_state = 'open'
        """,
        (source_id,),
    ).fetchall()
    unavailable_count = 0
    for row in rows:
        if row["source_job_id"] in seen_source_job_ids:
            continue
        missing = int(row["missing_successful_scan_count"]) + 1
        state = "unavailable" if missing >= 2 else "open"
        if state == "unavailable":
            unavailable_count += 1
        conn.execute(
            """
            UPDATE job_postings
            SET missing_successful_scan_count = ?, availability_state = ?
            WHERE id = ?
            """,
            (missing, state, int(row["id"])),
        )
    return unavailable_count


def ensure_review(conn: sqlite3.Connection, job_posting_id: int) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO opportunity_reviews (job_posting_id, state)
        VALUES (?, 'new')
        """,
        (job_posting_id,),
    )


def resurface_review_on_material_change(conn: sqlite3.Connection, job_posting_id: int) -> None:
    conn.execute(
        """
        UPDATE opportunity_reviews
        SET state = 'new',
            decision_reason = NULL,
            reviewed_at = NULL,
            snooze_until = NULL
        WHERE job_posting_id = ?
          AND state IN ('approved', 'dismissed', 'snoozed')
        """,
        (job_posting_id,),
    )


def wake_due_snoozes(conn: sqlite3.Connection, today: str) -> int:
    cursor = conn.execute(
        """
        UPDATE opportunity_reviews
        SET state = 'new',
            decision_reason = NULL,
            reviewed_at = NULL,
            snooze_until = NULL
        WHERE state = 'snoozed'
          AND snooze_until IS NOT NULL
          AND snooze_until <= ?
        """,
        (today,),
    )
    return cursor.rowcount


def record_source_run(
    conn: sqlite3.Connection,
    source_id: int,
    *,
    started_at: str,
    finished_at: str,
    status: str,
    http_status: int | None,
    fetched_count: int,
    new_count: int,
    changed_count: int,
    error_summary: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO source_runs (
          job_source_id, started_at, finished_at, status, http_status, fetched_count,
          new_count, changed_count, retry_count, error_summary
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (
            source_id,
            started_at,
            finished_at,
            status,
            http_status,
            fetched_count,
            new_count,
            changed_count,
            error_summary,
        ),
    )


def get_postings_by_ids(conn: sqlite3.Connection, posting_ids: list[int]) -> list[sqlite3.Row]:
    if not posting_ids:
        return []
    placeholders = ",".join("?" for _ in posting_ids)
    return conn.execute(
        f"SELECT * FROM job_postings WHERE id IN ({placeholders}) ORDER BY id",
        posting_ids,
    ).fetchall()


def persist_evaluation(
    conn: sqlite3.Connection,
    job_posting_id: int,
    input_hash: str,
    evaluation: RoleEvaluation,
    *,
    model_version: str | None = None,
) -> bool:
    stored_model_version = (
        model_version
        or evaluation.provenance.get("model_version")
        or evaluation.provenance.get("evaluator_version")
        or DEFAULT_EVALUATOR_VERSION
    )
    stored_prompt_version = evaluation.provenance.get(
        "prompt_version",
        load_scoring_policy().version,
    )
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO role_evaluations (
          job_posting_id, profile_version_id, location_policy_version_id, prompt_version,
          model_version, input_hash, evaluation_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_posting_id,
            load_candidate_profile().version,
            load_location_policy().version,
            stored_prompt_version,
            stored_model_version,
            input_hash,
            json.dumps(evaluation.to_jsonable(), sort_keys=True),
            utc_now(),
        ),
    )
    return cursor.rowcount > 0


def record_evaluation_skip(
    conn: sqlite3.Connection,
    job_posting_id: int,
    skipped_input_hash: str,
    reason: str,
) -> bool:
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO evaluation_skips (job_posting_id, input_hash, reason, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (job_posting_id, skipped_input_hash, reason, utc_now()),
    )
    return cursor.rowcount > 0


def get_digest_rows(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
) -> list[sqlite3.Row]:
    wake_due_snoozes(conn, utc_now()[:10])
    since_clause = ""
    params: tuple[str, ...] = ()
    if since is not None:
        since_clause = "AND re.created_at >= ?"
        params = (since,)
    return conn.execute(
        f"""
        SELECT
          jp.id AS job_id,
          js.source_type,
          js.source_key,
          jp.source_job_id,
          jp.canonical_key,
          c.name AS company,
          c.tier AS company_tier,
          jp.title,
          jp.locations_json,
          jp.department,
          jp.source_url,
          jp.first_seen_at,
          jp.posted_at,
          re.created_at AS evaluated_at,
          re.evaluation_json,
          orev.state AS review_state
        FROM job_postings jp
        JOIN job_sources js ON js.id = jp.source_id
        JOIN companies c ON c.id = jp.company_id
        JOIN opportunity_reviews orev ON orev.job_posting_id = jp.id
        JOIN role_evaluations re ON re.job_posting_id = jp.id
        WHERE orev.state = 'new'
          AND jp.availability_state = 'open'
          {since_clause}
          AND re.id = (
            SELECT MAX(id) FROM role_evaluations latest
            WHERE latest.job_posting_id = jp.id
          )
        ORDER BY c.tier, jp.first_seen_at DESC
        """,
        params,
    ).fetchall()


def latest_delivered_notification_at(
    conn: sqlite3.Connection,
    notification_type: str = "digest",
) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(sent_at) AS sent_at
        FROM notifications
        WHERE type = ?
          AND status IN ('sent', 'fallback')
        """,
        (notification_type,),
    ).fetchone()
    if row is None:
        return None
    return row["sent_at"]


def has_delivered_payload(
    conn: sqlite3.Connection,
    payload_hash: str,
    notification_type: str = "digest",
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM notifications
        WHERE type = ?
          AND payload_hash = ?
          AND status IN ('sent', 'fallback')
        LIMIT 1
        """,
        (notification_type, payload_hash),
    ).fetchone()
    return row is not None


def record_notification(
    conn: sqlite3.Connection,
    *,
    notification_type: str,
    payload_hash: str,
    status: str,
    error_summary: str | None = None,
    sent_at: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO notifications (type, payload_hash, sent_at, status, error_summary)
        VALUES (?, ?, ?, ?, ?)
        """,
        (notification_type, payload_hash, sent_at or utc_now(), status, error_summary),
    )
    return int(cursor.lastrowid)


def latest_source_failures(conn: sqlite3.Connection, limit: int = 5) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
          c.name AS company,
          js.source_type,
          js.source_key,
          js.health_status,
          latest.status,
          latest.error_summary,
          latest.finished_at,
          js.expected_volume_min
        FROM job_sources js
        JOIN companies c ON c.id = js.company_id
        LEFT JOIN (
          SELECT sr.*
          FROM source_runs sr
          WHERE sr.id = (
            SELECT MAX(newer.id)
            FROM source_runs newer
            WHERE newer.job_source_id = sr.job_source_id
          )
        ) latest ON latest.job_source_id = js.id
        WHERE js.health_status IN ('degraded', 'failing', 'unsupported')
           OR latest.status != 'success'
        ORDER BY COALESCE(latest.id, 0) DESC, c.tier, c.name
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
