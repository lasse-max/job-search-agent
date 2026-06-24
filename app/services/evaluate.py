"""Structured development evaluator for Checkpoint B.

This is intentionally deterministic. It validates the data path and mirrors the
required evaluation schema, but it is not the final LLM-backed evaluator.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3

from app.models import Alignment, CompanyConfig, Gap, HardBlocker, RoleEvaluation


TECHNICAL_ENGINEERING_TERMS = (
    "software engineer",
    "staff engineer",
    "forward deployed engineer",
    "full stack",
    "backend",
    "machine learning engineer",
)


def input_hash(row: sqlite3.Row) -> str:
    payload = {
        "title": row["title"],
        "locations": row["locations_json"],
        "department": row["department"],
        "description": row["description_text"],
        "raw_payload_hash": row["raw_payload_hash"],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def should_evaluate(row: sqlite3.Row, company: CompanyConfig) -> bool:
    """Keep the Databricks slice focused on target roles and locations."""

    title = row["title"].lower()
    department = (row["department"] or "").lower()
    locations = " ".join(json.loads(row["locations_json"])).lower()
    target_location = any(location.lower().split(" / ")[0] in locations for location in company.target_locations)
    role_signal = any(
        signal in f"{title} {department}"
        for signal in ("deployment strategist", "strategy", "operations", "professional services")
    )
    return target_location and role_signal


def evaluate_role(row: sqlite3.Row, company: CompanyConfig) -> RoleEvaluation:
    title = row["title"]
    title_lower = row["title"].lower()
    text = f"{row['title']} {row['department'] or ''} {row['description_text']}".lower()
    locations = json.loads(row["locations_json"])
    hard_blockers: list[HardBlocker] = []

    if any(term in title_lower for term in TECHNICAL_ENGINEERING_TERMS) or (
        "engineer" in title_lower and "strategist" not in title_lower
    ):
        hard_blockers.append(
            HardBlocker(
                type="technical_role",
                evidence="Posting centers on production engineering or forward-deployed engineering.",
            )
        )

    role_family_fit = _role_family_fit(title, row["department"] or "", text)
    evidence_strength = _evidence_strength(text)
    scope_seniority = _scope_seniority(title, text)
    gap_manageability = 35 if hard_blockers else _gap_manageability(text)

    dimensions = {
        "role_family_fit": role_family_fit,
        "evidence_strength": evidence_strength,
        "scope_seniority": scope_seniority,
        "gap_manageability": gap_manageability,
    }
    fit_score = round(
        role_family_fit * 0.30
        + evidence_strength * 0.30
        + scope_seniority * 0.25
        + gap_manageability * 0.15
    )
    feasibility_state, feasibility_reason = _feasibility(locations)
    recommendation = _recommendation(fit_score, feasibility_state, company, hard_blockers)

    return RoleEvaluation(
        role_fit_score=fit_score,
        confidence=0.68,
        dimensions=dimensions,
        feasibility={
            "state": "blocked" if hard_blockers else feasibility_state,
            "reason": "Technical blocker overrides feasibility." if hard_blockers else feasibility_reason,
            "policy_version": "location_policy_v1",
        },
        strategic_priority={
            "company_tier": f"tier_{company.tier}",
            "freshness": "new_today",
            "warm_path": company.warm_path,
            "reason": "Tier 1 company with a warm path in the tracker."
            if company.warm_path
            else f"Tier {company.tier} company from the configured watchlist.",
        },
        recommendation=recommendation,
        hard_blockers=hard_blockers,
        alignments=_alignments(title, text),
        gaps=_gaps(text, hard_blockers),
        uncertainties=[
            "This Checkpoint B evaluation uses deterministic rules, not the final LLM evaluator.",
            "Work authorization must be confirmed against the stored policy before applying.",
        ],
        summary=_summary(title, fit_score, recommendation, hard_blockers),
    )


def _role_family_fit(title: str, department: str, text: str) -> int:
    combined = f"{title} {department}".lower()
    if "deployment strategist" in combined:
        return 92
    if "strategy" in combined and "operations" in combined:
        return 86
    if "professional services operations" in combined:
        return 78
    if "customer success" in text or "account executive" in text:
        return 42
    return 58


def _evidence_strength(text: str) -> int:
    signals = {
        "stakeholder": 8,
        "cross-functional": 8,
        "customer": 6,
        "strategy": 8,
        "operations": 8,
        "executive": 6,
        "deployment": 7,
        "transformation": 7,
        "program": 5,
    }
    score = 54 + sum(weight for keyword, weight in signals.items() if keyword in text)
    return min(score, 88)


def _scope_seniority(title: str, text: str) -> int:
    title_lower = title.lower()
    if "associate" in title_lower or "intern" in title_lower:
        return 35
    score = 68
    if any(term in title_lower for term in ("senior", "manager", "lead", "strategist")):
        score += 10
    if "executive" in text or "leadership" in text:
        score += 6
    return min(score, 88)


def _gap_manageability(text: str) -> int:
    score = 78
    if "python" in text or "sql" in text:
        score -= 8
    if "technical" in text or "architecture" in text:
        score -= 8
    if "quota" in text:
        score -= 18
    return max(score, 45)


def _feasibility(locations: list[str]) -> tuple[str, str]:
    joined = " ".join(locations).lower()
    if any(place in joined for place in ("sydney", "australia")):
        return "uncertain", "Australia has a pathway in the policy, but current unrestricted authorization is not assumed."
    if "london" in joined or "united kingdom" in joined:
        return "uncertain", "UK status must be verified before treating the role as fully viable."
    if "united states" in joined or "california" in joined:
        return "sponsorship_required", "US roles require sponsorship or a credible transfer path."
    if any(place in joined for place in ("germany", "munich", "berlin")):
        return "viable", "EU/Germany authorization is marked high-confidence."
    return "uncertain", "Location is not explicitly mapped by the Checkpoint B deterministic policy."


def _recommendation(
    fit_score: int,
    feasibility_state: str,
    company: CompanyConfig,
    hard_blockers: list[HardBlocker],
) -> str:
    if hard_blockers or feasibility_state == "blocked":
        return "blocked"
    if fit_score >= 80 and company.tier <= 2:
        return "apply_now"
    if fit_score >= 70 and company.tier == 1 and company.warm_path:
        return "apply_now"
    if fit_score >= 65:
        return "consider"
    if fit_score >= 50 and company.tier <= 2:
        return "stretch"
    return "skip"


def _alignments(title: str, text: str) -> list[Alignment]:
    alignments = [
        Alignment(
            job_requirement="Lead ambiguous strategy and operations work.",
            candidate_evidence="Google Devices & Services strategy/operations background with global rollout and transformation programs.",
            evidence_strength="strong" if re.search("strategy|operations|deployment", text) else "medium",
        ),
        Alignment(
            job_requirement="Partner with technical and business stakeholders.",
            candidate_evidence="Zenith product work included BRDs, validation logic, Engineering partnership, UAT, training, and rollout.",
            evidence_strength="strong",
        ),
    ]
    if "deployment strategist" in title.lower():
        alignments.append(
            Alignment(
                job_requirement="Bridge customer problems into deployable technical solutions.",
                candidate_evidence="Claims-validation and Fitbit migration work show business problem framing through implementation.",
                evidence_strength="medium",
            )
        )
    return alignments


def _gaps(text: str, hard_blockers: list[HardBlocker]) -> list[Gap]:
    if hard_blockers:
        return [
            Gap(
                gap="Production engineering appears central to the role.",
                severity="high",
                mitigation="Do not pursue unless the posting is actually strategy-led rather than engineering-led.",
            )
        ]
    gaps = [
        Gap(
            gap="Direct external customer value-scoping is a stretch versus the candidate's internal product/operations background.",
            severity="medium",
            mitigation="Anchor the story in Zenith requirements, Engineering partnership, UAT, rollout, and measurable impact.",
        )
    ]
    if "technical" in text or "architecture" in text:
        gaps.append(
            Gap(
                gap="Technical depth may be tested.",
                severity="medium",
                mitigation="Prepare a clear boundary: business/product logic and implementation leadership, not production coding.",
            )
        )
    return gaps


def _summary(
    title: str,
    fit_score: int,
    recommendation: str,
    hard_blockers: list[HardBlocker],
) -> str:
    if hard_blockers:
        return f"{title} is blocked because engineering appears central, despite company fit."
    return f"{title} scores {fit_score}/100 with recommendation `{recommendation}` under the Checkpoint B deterministic evaluator."
