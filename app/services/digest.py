"""Local digest generation."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

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
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    trim_blocks=True,
    lstrip_blocks=True,
)
SECTION_STYLES = {
    "apply_now": {
        "label": "Apply now — the mark",
        "accent": "#e07a5c",
        "border": "#d65a3c",
        "score_color": "#f0876b",
        "score_bg": "#2a2530",
        "score_border": "#7d3d33",
    },
    "consider": {
        "label": "Consider",
        "accent": "#57b6c4",
        "border": "#1f6f7c",
        "score_color": "#7cc9d6",
        "score_bg": "#18333d",
        "score_border": "#2e7380",
    },
    "stretch": {
        "label": "Stretch / reach — calibration in progress, scrutinize",
        "accent": "#c7a86a",
        "border": "#9d854b",
        "score_color": "#d7bd7d",
        "score_bg": "#2b2a21",
        "score_border": "#6e613c",
    },
}


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
    return _render_template("digest.html.j2", rows, failures, selection)


def render_text(
    rows: list[sqlite3.Row],
    failures: list[sqlite3.Row],
    *,
    selection: DigestSelection | None = None,
) -> str:
    rows, selection = _render_inputs(rows, selection)
    return _render_template("digest.txt.j2", rows, failures, selection)


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


def _render_template(
    template_name: str,
    rows: list[sqlite3.Row],
    failures: list[sqlite3.Row],
    selection: DigestSelection,
) -> str:
    rendered = TEMPLATE_ENV.get_template(template_name).render(
        digest=_digest_context(rows, failures, selection)
    )
    return rendered.rstrip() + "\n"


def _digest_context(
    rows: list[sqlite3.Row],
    failures: list[sqlite3.Row],
    selection: DigestSelection,
) -> dict[str, Any]:
    generated_at = utc_now()
    grouped = _group_rows(rows)
    sections = []
    counts: dict[str, int] = {}
    for recommendation, default_label in RECOMMENDATION_SECTIONS:
        section_rows = _ranked_rows(grouped.get(recommendation, []))
        counts[recommendation] = len(section_rows)
        if not section_rows:
            continue
        style = SECTION_STYLES[recommendation]
        sections.append(
            {
                "key": recommendation,
                "label": style["label"],
                "default_label": default_label,
                "accent": style["accent"],
                "border": style["border"],
                "score_color": style["score_color"],
                "score_bg": style["score_bg"],
                "score_border": style["score_border"],
                "roles": [_role_context(row) for row in section_rows],
            }
        )

    low_priority_rows = [
        row
        for recommendation in LOW_PRIORITY_RECOMMENDATIONS
        for row in grouped.get(recommendation, [])
    ]
    ranked_low_priority = _ranked_delivery_rows(low_priority_rows)
    low_priority_limit = 6
    low_priority_roles = [
        _compact_role_context(row) for row in ranked_low_priority[:low_priority_limit]
    ]

    return {
        "generated_at": generated_at,
        "generated_label": _format_generated_label(generated_at),
        "sections": sections,
        "counts": {
            "apply_now": counts.get("apply_now", 0),
            "consider": counts.get("consider", 0),
            "stretch": counts.get("stretch", 0),
            "low_priority": len(low_priority_rows),
            "failures": len(failures),
            "shown": len(rows),
            "total": len(rows) + selection.overflow_count,
        },
        "low_priority": {
            "count": len(low_priority_rows),
            "roles": low_priority_roles,
            "overflow_count": max(0, len(ranked_low_priority) - len(low_priority_roles)),
        },
        "failures": [_failure_context(failure) for failure in failures],
        "selection": {
            "cap": selection.cap,
            "overflow_count": selection.overflow_count,
            "fallback_filtered_count": selection.fallback_filtered_count,
            "degraded": selection.degraded,
        },
        "review_command": "job-agent review list",
        "csv_command": "job-agent export",
    }


def _role_context(row: sqlite3.Row) -> dict[str, Any]:
    evaluation = json.loads(row["evaluation_json"])
    locations = _loads_list(row["locations_json"])
    feasibility = evaluation.get("feasibility") or {}
    priority = evaluation.get("strategic_priority") or {}
    hard_blockers = evaluation.get("hard_blockers") or []
    alignments = evaluation.get("alignments") or []
    gaps = evaluation.get("gaps") or []
    confidence = float(evaluation.get("confidence") or 0)
    recommendation = str(evaluation.get("recommendation") or "")
    return {
        "stable_id": _stable_id(row),
        "company": str(row["company"] or ""),
        "title": str(row["title"] or ""),
        "locations": locations,
        "locations_label": ", ".join(locations) if locations else "Unknown location",
        "department": str(row["department"] or "Unspecified"),
        "first_seen_at": str(row["first_seen_at"] or "unknown"),
        "posted_at": str(row["posted_at"] or "unknown"),
        "fit_score": _as_int(evaluation.get("role_fit_score")),
        "confidence_label": f"{confidence:.0%}",
        "feasibility_state": str(feasibility.get("state") or "unknown"),
        "feasibility_reason": str(feasibility.get("reason") or "No feasibility note."),
        "feasibility_good": str(feasibility.get("state") or "") == "viable",
        "tier": str(row["company_tier"] or "unknown"),
        "priority_reason": str(priority.get("reason") or "No priority reason recorded."),
        "recommendation": recommendation,
        "recommendation_label": _humanize(recommendation),
        "summary": str(evaluation.get("summary") or "No summary recorded."),
        "alignments": [
            {
                "job_requirement": str(item.get("job_requirement") or ""),
                "candidate_evidence": str(item.get("candidate_evidence") or ""),
                "evidence_strength": str(item.get("evidence_strength") or ""),
            }
            for item in alignments[:4]
            if isinstance(item, dict)
        ],
        "gaps": [
            {
                "gap": str(item.get("gap") or ""),
                "mitigation": str(item.get("mitigation") or ""),
                "severity": str(item.get("severity") or ""),
            }
            for item in gaps[:3]
            if isinstance(item, dict)
        ],
        "hard_blockers": [
            {
                "type": str(item.get("type") or "blocker"),
                "evidence": str(item.get("evidence") or ""),
            }
            for item in hard_blockers
            if isinstance(item, dict)
        ],
        "source_url": str(row["source_url"] or ""),
    }


def _compact_role_context(row: sqlite3.Row) -> dict[str, Any]:
    role = _role_context(row)
    return {
        "company": role["company"],
        "title": role["title"],
        "fit_score": role["fit_score"],
        "recommendation_label": role["recommendation_label"],
    }


def _failure_context(failure: sqlite3.Row) -> dict[str, str]:
    status = str(failure["status"] or failure["health_status"] or "unknown")
    return {
        "status": status,
        "company": str(failure["company"] or ""),
        "source_type": str(failure["source_type"] or ""),
        "source_key": str(failure["source_key"] or ""),
        "error_summary": str(failure["error_summary"] or "No error summary recorded."),
        "finished_at": str(failure["finished_at"] or "unknown"),
    }


def _format_generated_label(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.strftime("%a %d %b")


def _loads_list(value: str | None) -> list[str]:
    if not value:
        return []
    loaded = json.loads(value)
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded]


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _humanize(value: str) -> str:
    return value.replace("_", " ").strip().title() if value else "Unknown"


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


def _stable_id(row: sqlite3.Row) -> str:
    return f"{row['source_type']}:{row['source_key']}:{row['source_job_id']}"
