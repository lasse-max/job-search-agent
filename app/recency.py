"""Shared posting-age policy helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import RecencyPolicyConfig, load_recency_policy


def normalize_timestamp(value: object | None) -> datetime | None:
    """Read historical ISO dates/offsets as instants; unzoned values mean UTC."""
    if value is None or value == "":
        return None
    try:
        timestamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def posting_timestamp(posting: Any) -> datetime | None:
    return normalize_timestamp(
        _posting_value(posting, "posted_at") or _posting_value(posting, "first_seen_at")
    )


def utc_timestamp_sql(expression: str, *, postgres: bool = False) -> str:
    """Normalize a trusted SQL expression before filtering, sorting or LIMIT.

    SQLite has no timestamp type: julianday is its numeric UTC representation.
    Postgres must explicitly interpret unzoned history as UTC, not session time.
    The read-view expression is kept identical by a migration contract test.
    """
    if not postgres:
        return f"julianday({expression})"
    return (
        f"CASE WHEN {expression} ~ '[T ].*([Zz]|[+-][0-9]{{2}}(:[0-9]{{2}}|[0-9]{{2}}){{0,1}})$' "
        f"THEN CAST({expression} AS TIMESTAMP WITH TIME ZONE) "
        f"ELSE CAST({expression} AS TIMESTAMP) AT TIME ZONE 'UTC' END"
    )


def recency_cutoff_date(
    policy: RecencyPolicyConfig | None = None,
    *,
    now: datetime | None = None,
) -> str:
    policy = policy or load_recency_policy()
    return _cutoff_date(policy.max_age_days, now=now)


def backfill_cutoff_date(
    policy: RecencyPolicyConfig | None = None,
    *,
    now: datetime | None = None,
) -> str:
    """Bound rescoring more tightly without narrowing browse/digest freshness."""
    policy = policy or load_recency_policy()
    return _cutoff_date(policy.backfill_max_age_days, now=now)


def _cutoff_date(max_age_days: int, *, now: datetime | None) -> str:
    current = normalize_timestamp(now or datetime.now(timezone.utc))
    assert current is not None
    return (current.date() - timedelta(days=max_age_days)).isoformat()


def posting_is_recent(
    posting: Any,
    policy: RecencyPolicyConfig | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    effective_date = posting_timestamp(posting)
    if effective_date is None:
        return False
    cutoff = normalize_timestamp(recency_cutoff_date(policy, now=now))
    assert cutoff is not None
    return effective_date >= cutoff


def posting_freshness_label(
    posting: Any,
    *,
    now: datetime | None = None,
) -> str:
    posted_at = _posting_value(posting, "posted_at")
    effective_date = posting_timestamp(posting)
    prefix = "posted" if posted_at else "first seen"
    if effective_date is None:
        return f"{prefix} date unknown"
    current = normalize_timestamp(now or datetime.now(timezone.utc))
    assert current is not None
    age_days = max(0, (current.date() - effective_date.date()).days)
    return f"{prefix} today" if age_days == 0 else f"{prefix} {age_days}d ago"


def _posting_value(posting: Any, key: str) -> object | None:
    try:
        return posting[key]
    except (KeyError, TypeError, IndexError):
        getter = getattr(posting, "get", None)
        return getter(key) if getter else None
