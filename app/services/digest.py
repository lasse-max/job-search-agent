"""Local digest generation."""

from __future__ import annotations

import html
import json
import sqlite3
from pathlib import Path

from app.config import load_scoring_policy
from app.db import get_digest_rows, latest_source_failures
from app.models import utc_now


RECOMMENDATION_SECTIONS = [
    ("apply_now", "Apply now"),
    ("consider", "Consider"),
    ("stretch", "Stretch / selective"),
]
LOW_PRIORITY_RECOMMENDATIONS = {"skip", "blocked"}
FALLBACK_EVALUATOR_WARNING = "fallback evaluator — not validated"


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

    html_path.write_text(render_html(rows, failures), encoding="utf-8")
    text_path.write_text(render_text(rows, failures), encoding="utf-8")
    return html_path, text_path, len(rows)


def render_html(rows: list[sqlite3.Row], failures: list[sqlite3.Row]) -> str:
    grouped = _group_rows(rows)
    digest_limits = load_scoring_policy().digest_limits
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
    if uses_fallback_evaluator(rows):
        parts.append(
            "<div class='warning'><strong>Fallback evaluator — not validated.</strong> "
            "This local digest was rendered from deterministic fallback evaluations and "
            "must not be treated as a calibrated email digest.</div>"
        )
    for recommendation, label in RECOMMENDATION_SECTIONS:
        raw_section_rows = _ranked_rows(grouped.get(recommendation, []))
        section_limit = digest_limits.get(recommendation, len(raw_section_rows))
        section_rows = raw_section_rows[:section_limit]
        if not section_rows:
            continue
        parts.append(f"<h2>{html.escape(label)}</h2>")
        for row in section_rows:
            parts.append(_role_card(row))
        if len(raw_section_rows) > len(section_rows):
            parts.append(
                "<p class='muted'>"
                f"{len(raw_section_rows) - len(section_rows)} additional "
                f"{html.escape(label.lower())} roles hidden by the digest cap."
                "</p>"
            )
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


def render_text(rows: list[sqlite3.Row], failures: list[sqlite3.Row]) -> str:
    grouped = _group_rows(rows)
    digest_limits = load_scoring_policy().digest_limits
    parts = [f"Job Search Digest - generated {utc_now()}", ""]
    if uses_fallback_evaluator(rows):
        parts.append(FALLBACK_EVALUATOR_WARNING)
        parts.append("This local digest uses deterministic fallback evaluations.")
        parts.append("")
    for recommendation, label in RECOMMENDATION_SECTIONS:
        raw_section_rows = _ranked_rows(grouped.get(recommendation, []))
        section_limit = digest_limits.get(recommendation, len(raw_section_rows))
        section_rows = raw_section_rows[:section_limit]
        if not section_rows:
            continue
        parts.append(label)
        parts.append("-" * len(label))
        for row in section_rows:
            parts.extend(_role_text_lines(row))
        if len(raw_section_rows) > len(section_rows):
            parts.append(f"{len(raw_section_rows) - len(section_rows)} additional hidden by cap.")
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
    for row in rows:
        evaluation = json.loads(row["evaluation_json"])
        provenance = evaluation.get("provenance") or {}
        if str(provenance.get("fallback_quality")).lower() == "true":
            return True
        evaluator_version = str(provenance.get("evaluator_version") or "")
        model_version = str(provenance.get("model_version") or "")
        if "deterministic_fallback" in evaluator_version or "deterministic_fallback" in model_version:
            return True
    return False


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
