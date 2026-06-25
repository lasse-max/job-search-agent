"""Live-noise sampling for human precision labels."""

from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.config import load_company_config
from app.models import CompanyConfig, utc_now
from app.services.evaluate import relevance_decision


@dataclass(frozen=True)
class LiveNoiseSampleResult:
    output_path: Path
    sampled_count: int
    available_count: int


def sample_live_noise_set(
    conn: sqlite3.Connection,
    output_path: Path,
    *,
    sample_size: int = 150,
    seed: int = 7,
    gate_passers_only: bool = False,
) -> LiveNoiseSampleResult:
    """Write a deterministic label template from cached live postings."""

    rows = _candidate_rows(conn)
    if gate_passers_only:
        rows = _gate_passing_rows(rows)
    sampled = _sample_rows(rows, sample_size=sample_size, seed=seed)
    set_purpose = "gate_passer_precision" if gate_passers_only else "uniform_gate_recall"
    payload = {
        "version": "live_noise_labels_v1",
        "sampled_at": utc_now(),
        "sample_size_requested": sample_size,
        "sample_size_actual": len(sampled),
        "set_purpose": set_purpose,
        "source": "cached_sqlite_job_postings",
        "label_instructions": (
            "Fill expected_recommendation with apply_now, consider, stretch, skip, "
            "or blocked. Mark apply_now/consider only when the role belongs in the "
            "digest surface for this candidate."
        ),
        "live_noise_set": [
            _template_item(index, row, id_prefix="LNP" if gate_passers_only else "LN")
            for index, row in enumerate(sampled, 1)
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return LiveNoiseSampleResult(
        output_path=output_path,
        sampled_count=len(sampled),
        available_count=len(rows),
    )


def _candidate_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
          jp.id AS job_id,
          c.name AS company,
          c.tier AS company_tier,
          c.warm_path,
          js.source_type,
          js.source_key,
          jp.source_job_id,
          jp.title,
          jp.locations_json,
          jp.department,
          jp.employment_type,
          jp.description_text,
          jp.source_url,
          jp.posted_at,
          jp.first_seen_at
        FROM job_postings jp
        JOIN companies c ON c.id = jp.company_id
        JOIN job_sources js ON js.id = jp.source_id
        WHERE jp.availability_state = 'open'
        ORDER BY jp.id
        """
    ).fetchall()


def _gate_passing_rows(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    passing: list[sqlite3.Row] = []
    for row in rows:
        company = _company_for_row(row)
        if relevance_decision(row, company).should_evaluate:
            passing.append(row)
    return passing


def _company_for_row(row: sqlite3.Row) -> CompanyConfig:
    try:
        return load_company_config(str(row["company"]))
    except ValueError:
        return CompanyConfig(
            name=str(row["company"]),
            tier=int(row["company_tier"]),
            enabled=True,
            ats_type=str(row["source_type"]),
            source_key=str(row["source_key"]),
            careers_url=str(row["source_url"]),
            target_locations=json.loads(row["locations_json"]),
            target_role_family_notes="Live-noise sample row.",
            warm_path=bool(row["warm_path"]),
        )


def _sample_rows(
    rows: list[sqlite3.Row],
    *,
    sample_size: int,
    seed: int,
) -> list[sqlite3.Row]:
    if sample_size <= 0:
        return []
    shuffled = list(rows)
    random.Random(seed).shuffle(shuffled)
    return shuffled[:sample_size]


def _template_item(index: int, row: sqlite3.Row, *, id_prefix: str) -> dict[str, Any]:
    locations = json.loads(row["locations_json"])
    return {
        "id": f"{id_prefix}-{index:03d}",
        "job_posting_id": int(row["job_id"]),
        "stable_id": f"{row['source_type']}:{row['source_key']}:{row['source_job_id']}",
        "company": row["company"],
        "company_tier": int(row["company_tier"]),
        "role_title": row["title"],
        "department": row["department"] or "",
        "employment_type": row["employment_type"] or "",
        "location": "; ".join(locations),
        "posted_at": row["posted_at"] or "",
        "first_seen_at": row["first_seen_at"],
        "source_url": row["source_url"],
        "description_text": row["description_text"],
        "description_excerpt": _excerpt(row["description_text"]),
        "expected_recommendation": None,
        "expected_feasibility": None,
        "hard_blockers": [],
        "notes": "",
    }


def _excerpt(text: str, max_chars: int = 900) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."
