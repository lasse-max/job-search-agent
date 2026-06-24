"""Local digest generation."""

from __future__ import annotations

import html
import json
import sqlite3
from pathlib import Path

from app.db import get_digest_rows, latest_source_failures
from app.models import utc_now


RECOMMENDATION_SECTIONS = [
    ("apply_now", "Apply now"),
    ("consider", "Consider"),
    ("stretch", "Stretch / selective"),
    ("skip", "Blocked or low priority"),
    ("blocked", "Blocked or low priority"),
]


def write_digest(conn: sqlite3.Connection, output_dir: Path) -> tuple[Path, Path, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = get_digest_rows(conn)
    failures = latest_source_failures(conn)
    html_path = output_dir / "latest_digest.html"
    text_path = output_dir / "latest_digest.txt"

    html_path.write_text(render_html(rows, failures), encoding="utf-8")
    text_path.write_text(render_text(rows, failures), encoding="utf-8")
    return html_path, text_path, len(rows)


def render_html(rows: list[sqlite3.Row], failures: list[sqlite3.Row]) -> str:
    grouped = _group_rows(rows)
    parts = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>Job Search Digest</title>",
        "<style>body{font-family:Arial,sans-serif;max-width:980px;margin:32px auto;line-height:1.45}"
        ".card{border:1px solid #ddd;border-radius:10px;padding:16px;margin:12px 0}"
        ".muted{color:#666}.pill{display:inline-block;padding:2px 8px;border-radius:999px;background:#eee}</style>",
        "</head><body>",
        f"<h1>Job Search Digest</h1><p class='muted'>Generated {html.escape(utc_now())}</p>",
    ]
    for recommendation, label in RECOMMENDATION_SECTIONS:
        section_rows = grouped.get(recommendation, [])
        if not section_rows:
            continue
        parts.append(f"<h2>{html.escape(label)}</h2>")
        for row in section_rows:
            parts.append(_role_card(row))
    parts.append("<h2>Source failures and coverage gaps</h2>")
    if failures:
        parts.append("<ul>")
        for failure in failures:
            parts.append(
                "<li>"
                f"{html.escape(failure['source_type'])}:{html.escape(failure['source_key'])} "
                f"{html.escape(failure['status'])} - {html.escape(failure['error_summary'] or '')}"
                "</li>"
            )
        parts.append("</ul>")
    else:
        parts.append("<p class='muted'>No source failures recorded in this database.</p>")
    parts.append("</body></html>")
    return "\n".join(parts)


def render_text(rows: list[sqlite3.Row], failures: list[sqlite3.Row]) -> str:
    grouped = _group_rows(rows)
    parts = [f"Job Search Digest - generated {utc_now()}", ""]
    for recommendation, label in RECOMMENDATION_SECTIONS:
        section_rows = grouped.get(recommendation, [])
        if not section_rows:
            continue
        parts.append(label)
        parts.append("-" * len(label))
        for row in section_rows:
            evaluation = json.loads(row["evaluation_json"])
            locations = ", ".join(json.loads(row["locations_json"]))
            parts.append(
                f"[{row['job_id']}] {row['company']} - {row['title']} ({locations}) "
                f"fit={evaluation['role_fit_score']} recommendation={evaluation['recommendation']}"
            )
            parts.append(f"  {evaluation['summary']}")
            parts.append(f"  {row['source_url']}")
        parts.append("")
    parts.append("Source failures and coverage gaps")
    if failures:
        for failure in failures:
            parts.append(
                f"- {failure['source_type']}:{failure['source_key']} "
                f"{failure['status']} - {failure['error_summary'] or ''}"
            )
    else:
        parts.append("- None recorded")
    return "\n".join(parts) + "\n"


def _group_rows(rows: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        evaluation = json.loads(row["evaluation_json"])
        grouped.setdefault(evaluation["recommendation"], []).append(row)
    return grouped


def _role_card(row: sqlite3.Row) -> str:
    evaluation = json.loads(row["evaluation_json"])
    locations = ", ".join(json.loads(row["locations_json"]))
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
    return f"""
<div class="card">
  <h3>{html.escape(row['company'])} - {html.escape(row['title'])}</h3>
  <p><span class="pill">Job ID {row['job_id']}</span>
     <span class="pill">Fit {evaluation['role_fit_score']}</span>
     <span class="pill">{html.escape(evaluation['recommendation'])}</span>
     <span class="pill">{html.escape(evaluation['feasibility']['state'])}</span></p>
  <p><strong>Location:</strong> {html.escape(locations)}<br>
     <strong>Department:</strong> {html.escape(row['department'] or '')}<br>
     <strong>First seen:</strong> {html.escape(row['first_seen_at'])}</p>
  <p>{html.escape(evaluation['summary'])}</p>
  <p><strong>Alignments</strong></p><ul>{alignments}</ul>
  <p><strong>Gaps</strong></p><ul>{gaps}</ul>
  {f"<p><strong>Blockers</strong></p><ul>{blockers}</ul>" if blockers else ""}
  <p><a href="{html.escape(row['source_url'])}">Source role</a></p>
</div>
"""
