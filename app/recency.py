"""Shared posting-age policy helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.config import RecencyPolicyConfig, load_recency_policy


def recency_cutoff_date(
    policy: RecencyPolicyConfig | None = None,
    *,
    now: datetime | None = None,
) -> str:
    policy = policy or load_recency_policy()
    current = now or datetime.now(timezone.utc)
    return (current.date() - timedelta(days=policy.max_age_days)).isoformat()


def posting_is_recent(
    posting: Any,
    policy: RecencyPolicyConfig | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    effective_date = _posting_value(posting, "posted_at") or _posting_value(
        posting, "first_seen_at"
    )
    if not effective_date:
        return False
    return str(effective_date)[:10] >= recency_cutoff_date(policy, now=now)


def posting_freshness_label(
    posting: Any,
    *,
    now: datetime | None = None,
) -> str:
    posted_at = _posting_value(posting, "posted_at")
    first_seen_at = _posting_value(posting, "first_seen_at")
    effective_date = posted_at or first_seen_at
    prefix = "posted" if posted_at else "first seen"
    if not effective_date:
        return f"{prefix} date unknown"
    try:
        observed = date.fromisoformat(str(effective_date)[:10])
    except ValueError:
        return f"{prefix} date unknown"
    current = (now or datetime.now(timezone.utc)).date()
    age_days = max(0, (current - observed).days)
    return f"{prefix} today" if age_days == 0 else f"{prefix} {age_days}d ago"


def _posting_value(posting: Any, key: str) -> object | None:
    try:
        return posting[key]
    except (KeyError, TypeError, IndexError):
        getter = getattr(posting, "get", None)
        return getter(key) if getter else None
