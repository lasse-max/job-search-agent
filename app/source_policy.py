"""Current-source eligibility for live reads, separate from historical records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.config import load_watchlist


def source_exclusion_reason(source: Mapping[str, Any], watchlist=None) -> str | None:
    if str(source["health_status"]).lower() in {"disabled", "retired"}:
        return "source_disabled_or_retired"
    # Manual intake is owner-directed, not an automatic watchlist subscription.
    if source["source_type"] == "manual":
        return None
    if not source["enabled"]:
        return "company_disabled"
    companies = watchlist if watchlist is not None else load_watchlist()
    configured = next((item for item in companies if item["name"] == source["company"]), None)
    if configured is None:
        return "company_not_in_watchlist"
    if not configured.get("enabled"):
        return "watchlist_disabled"
    if (source["source_type"], source["source_key"]) != (
        configured.get("ats_type"), configured.get("source_key"),
    ):
        return "superseded_source"
    return None


def source_inventory(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT js.id AS source_id, js.source_type, js.source_key, js.health_status,
                  c.id AS company_id, c.name AS company, c.enabled
           FROM job_sources js JOIN companies c ON c.id = js.company_id
           ORDER BY js.id"""
    ).fetchall()
    return [dict(row) for row in rows]


def active_source_ids(conn) -> list[int]:
    watchlist = load_watchlist()
    return [int(row["source_id"]) for row in source_inventory(conn)
            if source_exclusion_reason(row, watchlist) is None]


def live_source_sql(conn, column: str = "jp.source_id") -> tuple[str, list[int]]:
    if column not in {"jp.source_id", "js.id"}:
        raise ValueError("Unsupported source column")
    ids = active_source_ids(conn)
    return (f"{column} IN ({','.join('?' for _ in ids)})", ids) if ids else ("1 = 0", [])
