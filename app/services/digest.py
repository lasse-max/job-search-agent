"""Local digest generation."""

from __future__ import annotations

import html
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.config import load_scoring_policy
from app.db import get_digest_rows, latest_source_failures
from app.models import utc_now


RECOMMENDATION_SECTIONS = [
    ("apply_now", "Apply now"),
    ("consider", "Consider"),
    ("stretch", "Stretch / reach — calibration in progress, scrutinize"),
]
LOW_PRIORITY_RECOMMENDATIONS = {"skip", "blocked"}
DEFAULT_DIGEST_MAX_ROLES = 25
ABSOLUTE_DIGEST_MAX_ROLES = 50


@dataclass(frozen=True)
class DigestSelection:
    rows: list[sqlite3.Row]
    cap: int
    overflow_count: int
    fallback_filtered_count: int
    degraded: bool


def write_digest(
    conn: sqlite3.Connection,
    output_dir: Path,
    *,
    since: str | None = None,
) -> tuple[Path, Path, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = get_digest_rows(conn, since=since)
    conn.commit()
    failures = latest_source_failures(conn)
    html_path = output_dir / "latest_digest.html"
    text_path = output_dir / "latest_digest.txt"

    selection = select_digest_rows(rows)
    html_path.write_text(
        render_html(
            selection.rows,
            failures,
            selection=selection,
        ),
        encoding="utf-8",
    )
    text_path.write_text(
        render_text(
            selection.rows,
            failures,
            selection=selection,
        ),
        encoding="utf-8",
    )
    return html_path, text_path, len(selection.rows)


def render_html(
    rows: list[sqlite3.Row],
    failures: list[sqlite3.Row],
    *,
    selection: DigestSelection | None = None,
) -> str:
    rows, selection = _render_inputs(rows, selection)
    grouped = _group_rows(rows)
    generated_at = utc_now()
    parts = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>Job Search Digest</title>",
        "<style>body{font-family:Arial,sans-serif;max-width:980px;margin:32px auto;line-height:1.45}"
        ".card{border:1px solid #ddd;border-radius:10px;padding:16px;margin:12px 0}"
        ".warning{background:#fff3cd;border:1px solid #ffe69c;border-radius:10px;padding:12px;margin:12px 0}"
        ".muted{color:#666}.pill{display:inline-block;padding:2px 8px;border-radius:999px;background:#eee;margin:2px}"
        ".meta{margin:6px 0}.low summary{cursor:pointer;font-weight:bold;font-size:1.2em;margin:18px 0 8px}</style>",
        "</head><body>",
        f"<h1>Job Search Digest</h1><p class='muted'>Generated {html.escape(generated_at)}</p>",
    ]
    if selection.degraded:
        parts.append(
            "<div class='warning'><strong>⚠️ DEGRADED — unvalidated.</strong> "
            "This digest was rendered from deterministic fallback evaluations; "
            "ranking is not trustworthy.</div>"
        )
    if selection.fallback_filtered_count:
        parts.append(
            "<div class='warning'><strong>Fallback rows withheld.</strong> "
            f"{selection.fallback_filtered_count} unvalidated role"
            f"{'s were' if selection.fallback_filtered_count != 1 else ' was'} "
            "dropped from this normal email.</div>"
        )
    if selection.overflow_count:
        parts.append(
            "<div class='warning'><strong>"
            f"Showing {len(rows)} of {len(rows) + selection.overflow_count} roles.</strong> "
            f"➕ {selection.overflow_count} more — view full list with "
            "<code>job-agent review list</code> or CSV exports.</div>"
        )
    for recommendation, label in RECOMMENDATION_SECTIONS:
        raw_section_rows = _ranked_rows(grouped.get(recommendation, []))
        section_rows = raw_section_rows
        if not section_rows:
            continue
        parts.append(f"<h2>{html.escape(label)}</h2>")
        for row in section_rows:
            parts.append(_role_card(row))
    low_priority = [
        row
        for recommendation in LOW_PRIORITY_RECOMMENDATIONS
        for row in grouped.get(recommendation, [])
    ]
    if low_priority:
        parts.append(
            "<p class='muted'><strong>Low-priority / blocked:</strong> "
            f"{len(low_priority)} role{'s' if len(low_priority) != 1 else ''} "
            "not expanded in this digest.</p>"
        )
    parts.append("<h2>Source failures and coverage gaps</h2>")
    if failures:
        parts.append("<ul>")
        for failure in failures:
            status = failure["status"] or failure["health_status"]
            parts.append(
                "<li>"
                f"<strong>{html.escape(status)}</strong> - "
                f"{html.escape(failure['company'])} "
                f"({html.escape(failure['source_type'])}:{html.escape(failure['source_key'])}) "
                f"{html.escape(failure['error_summary'] or '')}"
                "</li>"
            )
        parts.append("</ul>")
    else:
        parts.append("<p class='muted'>No source failures recorded in this database.</p>")
    parts.append("</body></html>")
    return "\n".join(parts)


def render_text(
    rows: list[sqlite3.Row],
    failures: list[sqlite3.Row],
    *,
    selection: DigestSelection | None = None,
) -> str:
    rows, selection = _render_inputs(rows, selection)
    grouped = _group_rows(rows)
    parts = [f"Job Search Digest - generated {utc_now()}", ""]
    if selection.degraded:
        parts.append("⚠️ DEGRADED — unvalidated")
        parts.append(
            "This digest uses deterministic fallback evaluations; ranking is not trustworthy."
        )
        parts.append("")
    if selection.fallback_filtered_count:
        parts.append(
            f"Fallback rows withheld: {selection.fallback_filtered_count} "
            "unvalidated role(s) dropped from this normal email."
        )
        parts.append("")
    if selection.overflow_count:
        parts.append(
            f"Showing {len(rows)} of {len(rows) + selection.overflow_count} roles. "
            f"➕ {selection.overflow_count} more — view full list with "
            "job-agent review list or CSV exports."
        )
        parts.append("")
    for recommendation, label in RECOMMENDATION_SECTIONS:
        raw_section_rows = _ranked_rows(grouped.get(recommendation, []))
        section_rows = raw_section_rows
        if not section_rows:
            continue
        parts.append(label)
        parts.append("-" * len(label))
        for row in section_rows:
            parts.extend(_role_text_lines(row))
        parts.append("")
    low_priority = [
        row
        for recommendation in LOW_PRIORITY_RECOMMENDATIONS
        for row in grouped.get(recommendation, [])
    ]
    if low_priority:
        parts.append(f"Low-priority / blocked: {len(low_priority)} not expanded")
        parts.append("")
    parts.append("Source failures and coverage gaps")
    if failures:
        for failure in failures:
            status = failure["status"] or failure["health_status"]
            parts.append(
                f"- {status} - {failure['company']} "
                f"({failure['source_type']}:{failure['source_key']}) "
                f"{failure['error_summary'] or ''}"
            )
    else:
        parts.append("- None recorded")
    return "\n".join(parts) + "\n"


def uses_fallback_evaluator(rows: list[sqlite3.Row]) -> bool:
    return any(is_fallback_evaluator_row(row) for row in rows)


def is_fallback_evaluator_row(row: sqlite3.Row) -> bool:
    evaluation = json.loads(row["evaluation_json"])
    provenance = evaluation.get("provenance") or {}
    if str(provenance.get("fallback_quality")).lower() == "true":
        return True
    evaluator_version = str(provenance.get("evaluator_version") or "")
    model_version = str(provenance.get("model_version") or "")
    return "deterministic_fallback" in evaluator_version or "deterministic_fallback" in model_version


def select_digest_rows(rows: list[sqlite3.Row]) -> DigestSelection:
    cap = digest_max_roles()
    valid_rows = [row for row in rows if not is_fallback_evaluator_row(row)]
    fallback_rows = [row for row in rows if is_fallback_evaluator_row(row)]
    degraded = not valid_rows and bool(fallback_rows)
    candidate_rows = fallback_rows if degraded else valid_rows
    ranked = _ranked_delivery_rows(candidate_rows)
    selected = ranked[:cap]
    return DigestSelection(
        rows=selected,
        cap=cap,
        overflow_count=max(0, len(ranked) - len(selected)),
        fallback_filtered_count=0 if degraded else len(fallback_rows),
        degraded=degraded,
    )


def _render_inputs(
    rows: list[sqlite3.Row],
    selection: DigestSelection | None,
) -> tuple[list[sqlite3.Row], DigestSelection]:
    if selection is None:
        selection = select_digest_rows(rows)
        return selection.rows, selection

    cap = max(1, min(int(selection.cap), ABSOLUTE_DIGEST_MAX_ROLES))
    overflow_count = max(selection.overflow_count, max(0, len(rows) - cap))
    render_rows = rows[:cap]
    return render_rows, DigestSelection(
        rows=render_rows,
        cap=cap,
        overflow_count=overflow_count,
        fallback_filtered_count=selection.fallback_filtered_count,
        degraded=selection.degraded,
    )


def digest_max_roles() -> int:
    configured = load_scoring_policy().digest_limits.get("max_roles", DEFAULT_DIGEST_MAX_ROLES)
    return max(1, min(int(configured), ABSOLUTE_DIGEST_MAX_ROLES))


def _ranked_delivery_rows(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    recommendation_rank = {
        "apply_now": 0,
        "consider": 1,
        "stretch": 2,
        "skip": 3,
        "blocked": 4,
    }
    return sorted(
        rows,
        key=lambda row: (
            recommendation_rank.get(json.loads(row["evaluation_json"])["recommendation"], 99),
            -int(json.loads(row["evaluation_json"])["role_fit_score"]),
            str(row["company"]),
            str(row["title"]),
        ),
    )

def _group_rows(rows: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        evaluation = json.loads(row["evaluation_json"])
        grouped.setdefault(evaluation["recommendation"], []).append(row)
    return grouped


def _ranked_rows(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    return sorted(
        rows,
        key=lambda row: int(json.loads(row["evaluation_json"])["role_fit_score"]),
        reverse=True,
    )


def _role_card(row: sqlite3.Row) -> str:
    evaluation = json.loads(row["evaluation_json"])
    locations = ", ".join(json.loads(row["locations_json"]))
    feasibility = evaluation["feasibility"]
    priority = evaluation["strategic_priority"]
    alignments = "".join(
        f"<li><strong>{html.escape(item['job_requirement'])}</strong>: "
        f"{html.escape(item['candidate_evidence'])} "
        f"<span class='muted'>({html.escape(item['evidence_strength'])})</span></li>"
        for item in evaluation["alignments"][:4]
    )
    gaps = "".join(
        f"<li><strong>{html.escape(item['gap'])}</strong>: "
        f"{html.escape(item['mitigation'])} "
        f"<span class='muted'>({html.escape(item['severity'])})</span></li>"
        for item in evaluation["gaps"][:3]
    )
    blockers = "".join(
        f"<li>{html.escape(item['type'])}: {html.escape(item['evidence'])}</li>"
        for item in evaluation["hard_blockers"]
    )
    stable_id = _stable_id(row)
    confidence = f"{float(evaluation['confidence']):.0%}"
    posted_at = row["posted_at"] or "unknown"
    return f"""
<div class="card">
  <h3>{html.escape(row['company'])} - {html.escape(row['title'])}</h3>
  <p><span class="pill">Stable ID {html.escape(stable_id)}</span>
     <span class="pill">Fit {evaluation['role_fit_score']}</span>
     <span class="pill">Confidence {html.escape(confidence)}</span>
     <span class="pill">{html.escape(evaluation['recommendation'])}</span>
     <span class="pill">{html.escape(feasibility['state'])}</span>
     <span class="pill">Tier {html.escape(str(row['company_tier']))}</span></p>
  <p class="meta"><strong>Location:</strong> {html.escape(locations)}<br>
     <strong>Department:</strong> {html.escape(row['department'] or '')}<br>
     <strong>First seen:</strong> {html.escape(row['first_seen_at'])}<br>
     <strong>Posted:</strong> {html.escape(posted_at)}</p>
  <p>{html.escape(evaluation['summary'])}</p>
  <p><strong>Priority reason:</strong> {html.escape(str(priority['reason']))}</p>
  <p><strong>Feasibility:</strong> {html.escape(feasibility['state'])} - {html.escape(feasibility['reason'])}</p>
  <p><strong>Alignments</strong></p><ul>{alignments}</ul>
  <p><strong>Gaps</strong></p><ul>{gaps}</ul>
  {f"<p><strong>Blockers</strong></p><ul>{blockers}</ul>" if blockers else ""}
  <p><a href="{html.escape(row['source_url'])}">Source role</a></p>
</div>
"""


def _role_text_lines(row: sqlite3.Row) -> list[str]:
    evaluation = json.loads(row["evaluation_json"])
    locations = ", ".join(json.loads(row["locations_json"]))
    feasibility = evaluation["feasibility"]
    priority = evaluation["strategic_priority"]
    stable_id = _stable_id(row)
    lines = [
        (
            f"[{stable_id}] {row['company']} - {row['title']} ({locations}) "
            f"fit={evaluation['role_fit_score']} confidence={float(evaluation['confidence']):.0%} "
            f"recommendation={evaluation['recommendation']}"
        ),
        f"  First seen: {row['first_seen_at']} | Posted: {row['posted_at'] or 'unknown'}",
        f"  Feasibility: {feasibility['state']} - {feasibility['reason']}",
        f"  Tier {row['company_tier']}: {priority['reason']}",
        f"  {evaluation['summary']}",
    ]
    for alignment in evaluation["alignments"][:4]:
        lines.append(
            "  Alignment: "
            f"{alignment['job_requirement']} -> {alignment['candidate_evidence']} "
            f"({alignment['evidence_strength']})"
        )
    for gap in evaluation["gaps"][:3]:
        lines.append(
            f"  Gap: {gap['gap']} -> {gap['mitigation']} ({gap['severity']})"
        )
    for blocker in evaluation["hard_blockers"]:
        lines.append(f"  Blocker: {blocker['type']} - {blocker['evidence']}")
    lines.append(f"  Source: {row['source_url']}")
    return lines


def _stable_id(row: sqlite3.Row) -> str:
    return f"{row['source_type']}:{row['source_key']}:{row['source_job_id']}"
