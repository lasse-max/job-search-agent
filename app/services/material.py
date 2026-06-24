"""Material job-content hashing shared by persistence and evaluation caching."""

from __future__ import annotations

import hashlib
import json
import sqlite3

from app.adapters.utils import clean_html, compact_text
from app.models import JobPosting


def material_hash_for_row(row: sqlite3.Row) -> str:
    return material_hash(
        title=row["title"],
        locations=json.loads(row["locations_json"]),
        description_text=row["description_text"],
        department=row["department"],
        employment_type=row["employment_type"],
    )


def material_hash_for_posting(posting: JobPosting) -> str:
    return material_hash(
        title=posting.title,
        locations=posting.locations,
        description_text=posting.description_text,
        department=posting.department,
        employment_type=posting.employment_type,
    )


def material_hash(
    *,
    title: str,
    locations: list[str],
    description_text: str,
    department: str | None,
    employment_type: str | None,
) -> str:
    payload = {
        "title": _normalize_text(title),
        "locations": sorted(_normalize_text(location) for location in locations),
        "description_text": _normalize_text(clean_html(description_text)),
        "department": _normalize_text(department or ""),
        "employment_type": _normalize_text(employment_type or ""),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _normalize_text(value: str) -> str:
    return compact_text(value).casefold()
