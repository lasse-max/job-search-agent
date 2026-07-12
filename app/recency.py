"""Shared posting-age policy helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def _posting_value(posting: Any, key: str) -> object | None:
    try:
        return posting[key]
    except (KeyError, TypeError, IndexError):
        getter = getattr(posting, "get", None)
        return getter(key) if getter else None
