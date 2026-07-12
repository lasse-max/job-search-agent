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
from app.db import ScanReach, get_digest_rows, latest_scan_reach, latest_source_failures
from app.models import utc_now
from app.recency import posting_freshness_label
from app.services.evaluate import HYBRID_EVALUATOR_VERSION
from app.services.text_rules import strip_location_variant_suffix


RECOMMENDATION_SECTIONS = [
    ("apply_now", "Apply now"),
    ("consider", "Consider"),
    ("stretch", "Stretch / reach — calibration in progress, scrutinize"),
]
STRONG_RECOMMENDATIONS = {recommendation for recommendation, _ in RECOMMENDATION_SECTIONS}
LOW_PRIORITY_RECOMMENDATIONS = {"skip", "blocked"}
DEFAULT_DIGEST_MAX_ROLES = 25
DEFAULT_DIGEST_MAX_PER_COMPANY = 3
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
    rows = get_digest_rows(conn, since=since, evaluator_version=HYBRID_EVALUATOR_VERSION)
    conn.commit()
    failures = latest_source_failures(conn)
    html_path = output_dir / "latest_digest.html"
    text_path = output_dir / "latest_digest.txt"

    selection = select_digest_rows(rows)
    scan_reach = latest_scan_reach(conn)
    html_path.write_text(
        render_html(
            selection.rows,
            failures,
            selection=selection,
            scan_reach=scan_reach,
        ),
        encoding="utf-8",
    )
    text_path.write_text(
        render_text(
            selection.rows,
            failures,
            selection=selection,
            scan_reach=scan_reach,
        ),
        encoding="utf-8",
    )
    return html_path, text_path, len(selection.rows)


def render_html(
    rows: list[sqlite3.Row],
    failures: list[sqlite3.Row],
    *,
    selection: DigestSelection | None = None,
    scan_reach: ScanReach | None = None,
) -> str:
    rows, selection = _render_inputs(rows, selection)
    return _render_template("digest.html.j2", rows, failures, selection, scan_reach)


def render_text(
    rows: list[sqlite3.Row],
    failures: list[sqlite3.Row],
    *,
    selection: DigestSelection | None = None,
    scan_reach: ScanReach | None = None,
) -> str:
    rows, selection = _render_inputs(rows, selection)
    return _render_template("digest.txt.j2", rows, failures, selection, scan_reach)


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


def select_digest_rows(
    rows: list[sqlite3.Row],
) -> DigestSelection:
    cap = digest_max_roles()
    valid_rows = [row for row in rows if not is_fallback_evaluator_row(row)]
    fallback_rows = [row for row in rows if is_fallback_evaluator_row(row)]
    degraded = not valid_rows and bool(fallback_rows)
    candidate_rows = fallback_rows if degraded else valid_rows
    ranked = _merge_location_variant_rows(_ranked_delivery_rows(candidate_rows))
    surfaced_rows = [
        row for row in ranked if _recommendation(row) in STRONG_RECOMMENDATIONS
    ]
    low_priority_rows = [
        row for row in ranked if _recommendation(row) in LOW_PRIORITY_RECOMMENDATIONS
    ]
    selected_surfaced_rows = _company_diverse_rows(
        surfaced_rows,
        limit=cap,
        max_per_company=digest_max_per_company(),
    )
    selected = selected_surfaced_rows + low_priority_rows
    return DigestSelection(
        rows=selected,
        cap=cap,
        overflow_count=max(0, len(surfaced_rows) - len(selected_surfaced_rows)),
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
    merged_rows = _merge_location_variant_rows(_ranked_delivery_rows(rows))
    surfaced_rows = [
        row for row in merged_rows if _recommendation(row) in STRONG_RECOMMENDATIONS
    ]
    low_priority_rows = [
        row for row in merged_rows if _recommendation(row) in LOW_PRIORITY_RECOMMENDATIONS
    ]
    rendered_surfaced_rows = _company_diverse_rows(
        surfaced_rows,
        limit=cap,
        max_per_company=digest_max_per_company(),
    )
    render_rows = rendered_surfaced_rows + low_priority_rows
    overflow_count = max(
        selection.overflow_count,
        max(0, len(surfaced_rows) - len(rendered_surfaced_rows)),
    )
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
    scan_reach: ScanReach | None,
) -> str:
    rendered = TEMPLATE_ENV.get_template(template_name).render(
        digest=_digest_context(rows, failures, selection, scan_reach)
    )
    return rendered.rstrip() + "\n"


def _digest_context(
    rows: list[sqlite3.Row],
    failures: list[sqlite3.Row],
    selection: DigestSelection,
    scan_reach: ScanReach | None,
) -> dict[str, Any]:
    generated_at = utc_now()
    scan_reach = scan_reach or ScanReach(fetched_count=0, company_count=0)
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
    shown_card_count = (
        counts.get("apply_now", 0)
        + counts.get("consider", 0)
        + counts.get("stretch", 0)
    )

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
            "shown": shown_card_count,
            "total": shown_card_count + selection.overflow_count,
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
        "scan_reach": {
            "fetched_count": scan_reach.fetched_count,
            "fetched_count_label": f"{scan_reach.fetched_count:,}",
            "company_count": scan_reach.company_count,
            "company_word": "company" if scan_reach.company_count == 1 else "companies",
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
        "freshness_label": posting_freshness_label(row),
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
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _humanize(value: str) -> str:
    return value.replace("_", " ").strip().title() if value else "Unknown"


def digest_max_roles() -> int:
    configured = load_scoring_policy().digest_limits.get("max_roles", DEFAULT_DIGEST_MAX_ROLES)
    return max(1, min(int(configured), ABSOLUTE_DIGEST_MAX_ROLES))


def digest_max_per_company() -> int:
    configured = load_scoring_policy().digest_limits.get(
        "max_per_company",
        DEFAULT_DIGEST_MAX_PER_COMPANY,
    )
    return max(1, min(int(configured), ABSOLUTE_DIGEST_MAX_ROLES))


def _company_diverse_rows(
    rows: list[sqlite3.Row],
    *,
    limit: int,
    max_per_company: int,
) -> list[sqlite3.Row]:
    selected: list[sqlite3.Row] = []
    company_counts: dict[str, int] = {}
    for row in rows:
        company_key = str(row["company"]).casefold().strip()
        if company_counts.get(company_key, 0) >= max_per_company:
            continue
        selected.append(row)
        company_counts[company_key] = company_counts.get(company_key, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def _merge_location_variant_rows(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    """Collapse proven, materially-compatible location title variants."""

    grouped: dict[tuple[str, str, str], list[sqlite3.Row]] = {}
    order: list[tuple[str, str, str]] = []
    for row in rows:
        locations = _loads_list(str(row["locations_json"] or "[]"))
        title = str(row["title"])
        base_title = strip_location_variant_suffix(title, locations)
        material_key = _delivery_material_signature(row)
        key = (
            str(row["company"]).casefold().strip(),
            base_title.casefold().strip(),
            "|".join(
                [
                    str(row["department"] or "").casefold().strip(),
                    str(row["employment_type"] or "").casefold().strip(),
                    material_key,
                ]
            ),
        )
        if key not in grouped:
            order.append(key)
            grouped[key] = []
        grouped[key].append(row)

    merged: list[sqlite3.Row] = []
    for key in order:
        group = grouped[key]
        if len(group) == 1:
            merged.append(group[0])
            continue
        explicit_variant = any(
            strip_location_variant_suffix(
                str(row["title"]),
                _loads_list(str(row["locations_json"] or "[]")),
            ).casefold()
            != str(row["title"]).casefold().strip()
            for row in group
        )
        distinct_locations = {
            location.casefold().strip()
            for row in group
            for location in _loads_list(str(row["locations_json"] or "[]"))
        }
        if not explicit_variant and len(distinct_locations) <= 1:
            merged.extend(group)
            continue
        representative = dict(group[0])
        representative["title"] = strip_location_variant_suffix(
            str(group[0]["title"]),
            _loads_list(str(group[0]["locations_json"] or "[]")),
        )
        locations: list[str] = []
        for row in group:
            for location in _loads_list(str(row["locations_json"] or "[]")):
                if location not in locations:
                    locations.append(location)
        representative["locations_json"] = json.dumps(locations)
        merged.append(representative)  # type: ignore[arg-type]
    return merged


def _delivery_material_signature(row: sqlite3.Row) -> str:
    evaluation = json.loads(row["evaluation_json"])
    blocker_types = sorted(
        str(blocker.get("type") or "")
        for blocker in evaluation.get("hard_blockers") or []
        if isinstance(blocker, dict)
    )
    feasibility = evaluation.get("feasibility") or {}
    alignments = evaluation.get("alignments") or []
    gaps = evaluation.get("gaps") or []
    return json.dumps(
        {
            "recommendation": evaluation.get("recommendation"),
            "estimated_level": evaluation.get("estimated_level"),
            "blockers": blocker_types,
            "feasibility": feasibility.get("state"),
            "alignment_requirements": [
                alignment.get("job_requirement")
                for alignment in alignments
                if isinstance(alignment, dict)
            ],
            "gaps": [gap.get("gap") for gap in gaps if isinstance(gap, dict)],
        },
        sort_keys=True,
    )


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


def _recommendation(row: sqlite3.Row) -> str:
    return str(json.loads(row["evaluation_json"])["recommendation"])


def _opportunity_key(row: sqlite3.Row) -> tuple[str, str, str]:
    locations = _loads_list(str(row["locations_json"] or "[]"))
    return (
        str(row["company"]).casefold().strip(),
        strip_location_variant_suffix(str(row["title"]), locations).casefold().strip(),
        str(row["department"] or "").casefold().strip(),
    )


def _ranked_rows(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    return sorted(
        rows,
        key=lambda row: int(json.loads(row["evaluation_json"])["role_fit_score"]),
        reverse=True,
    )


def _stable_id(row: sqlite3.Row) -> str:
    return f"{row['source_type']}:{row['source_key']}:{row['source_job_id']}"
