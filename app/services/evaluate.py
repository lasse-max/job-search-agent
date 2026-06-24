"""Structured development evaluator for Checkpoint B.

This is intentionally deterministic. It validates the data path and mirrors the
required evaluation schema, but it is not the final LLM-backed evaluator.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.config import load_relevance_filter
from app.models import Alignment, CompanyConfig, Gap, HardBlocker, RoleEvaluation


EVALUATOR_VERSION = "uncalibrated_dev_stub_v1"

TECHNICAL_ENGINEERING_TERMS = (
    "software engineer",
    "staff engineer",
    "forward deployed engineer",
    "full stack",
    "backend",
    "machine learning engineer",
)

PRIMARY_FAMILY_PATTERNS = (
    r"\bs\s*&\s*o\b",
    r"\bstrateg\w*\s*(?:&|and)?\s*operations\b",
    r"\bbusiness operations\b",
    r"\bbusiness ops\b",
    r"\bbizops\b",
    r"\bproduct operations\b",
    r"\bproduct ops\b",
    r"\bproduct strateg\w*\b",
    r"\bgtm\b",
    r"\bgo-to-market\b",
    r"\b(?:gtm|sales)\s+s\s*&\s*o\b",
    r"\bsales strateg\w*\s*(?:&|and)?\s*operations\b",
    r"\brevenue operations\b",
    r"\brevenue ops\b",
    r"\brevops\b",
    r"\bbusiness transformation\b",
    r"\bstrategic programs?\b",
    r"\bprogram(?:me)?\b",
    r"\bchief of staff\b",
)

STRETCH_FAMILY_PATTERNS = (
    r"\bdeployment strategist\b",
    r"\bforward[- ]deployed strateg\w*\b",
    r"\bprofessional services operations\b",
)


@dataclass(frozen=True)
class RelevanceDecision:
    should_evaluate: bool
    reason: str


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
    """Compatibility wrapper around the logged relevance decision."""

    return relevance_decision(row, company).should_evaluate


def relevance_decision(row: sqlite3.Row, company: CompanyConfig) -> RelevanceDecision:
    """Keep the slice focused while recording why a posting was skipped."""

    filter_config = load_relevance_filter()
    locations = json.loads(row["locations_json"])
    if filter_config.target_location_required and not _matches_target_location(
        locations,
        company.target_locations,
    ):
        return RelevanceDecision(False, "non_target_location")

    text = _role_text(row)
    if not _matches_any(text, filter_config.role_family_patterns):
        return RelevanceDecision(False, "no_primary_or_stretch_family_signal")

    return RelevanceDecision(True, "matched_target_location_and_role_family")


def evaluate_role(row: sqlite3.Row, company: CompanyConfig) -> RoleEvaluation:
    title = row["title"]
    title_lower = row["title"].lower()
    text = _role_text(row)
    locations = json.loads(row["locations_json"])
    hard_blockers = _technical_blockers(title_lower)

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
    is_stretch = _is_stretch_family(title, row["department"] or "", text)
    recommendation = _recommendation(
        fit_score,
        feasibility_state,
        company,
        hard_blockers,
        stretch_family=is_stretch,
    )
    policy_version = _config_version("location_policy.yaml", "location_policy_unknown")

    return RoleEvaluation(
        role_fit_score=fit_score,
        confidence=0.68,
        dimensions=dimensions,
        feasibility={
            "state": "blocked" if hard_blockers else feasibility_state,
            "reason": "Technical blocker overrides feasibility."
            if hard_blockers
            else feasibility_reason,
            "policy_version": policy_version,
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
            f"This Checkpoint B evaluation uses {EVALUATOR_VERSION}, not the final LLM evaluator.",
            "Work authorization must be confirmed against the stored policy before applying.",
        ],
        summary=_summary(title, fit_score, recommendation, hard_blockers),
    )


def _role_family_fit(title: str, department: str, text: str) -> int:
    combined = f"{title} {department}".lower()
    if _is_stretch_family(title, department, text):
        return 78
    if _matches_any(combined, PRIMARY_FAMILY_PATTERNS) or _matches_any(
        text,
        PRIMARY_FAMILY_PATTERNS,
    ):
        return 92
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
    if "intern" in title_lower:
        return 35
    score = 68
    if "associate" in title_lower:
        score -= 4
    if any(term in title_lower for term in ("senior", "manager", "lead", "strategist")):
        score += 10
    if any(
        term in text
        for term in ("executive", "leadership", "own", "drive", "cross-functional")
    ):
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
        return (
            "viable",
            "Australia is viable; spouse-visa work eligibility has an estimated "
            "three-month lead time from arrival.",
        )
    if "london" in joined or "united kingdom" in joined:
        return (
            "viable",
            "UK is viable; Skilled Worker sponsorship is needed but routine for "
            "German candidates at sponsoring employers.",
        )
    if "singapore" in joined:
        return (
            "viable",
            "Singapore is viable with sponsorship; COMPASS is noted but not a down-rank "
            "in the dev evaluator.",
        )
    if "united states" in joined or "california" in joined:
        return (
            "sponsorship_required",
            "US is the high-friction market; require credible sponsorship, transfer path, "
            "or warm route.",
        )
    if any(place in joined for place in ("germany", "munich", "berlin")):
        return "viable", "EU/Germany authorization is marked high-confidence."
    return (
        "uncertain",
        "Location is not explicitly mapped by the Checkpoint B deterministic policy.",
    )


def _recommendation(
    fit_score: int,
    feasibility_state: str,
    company: CompanyConfig,
    hard_blockers: list[HardBlocker],
    *,
    stretch_family: bool = False,
    exceptional_upside: bool = False,
) -> str:
    if hard_blockers or feasibility_state == "blocked":
        return "blocked"

    if stretch_family:
        if fit_score >= 70 and company.tier == 1 and (company.warm_path or exceptional_upside):
            return "apply_now"
        if fit_score >= 65:
            return "consider"
        if fit_score >= 50 and company.tier <= 2:
            return "stretch"
        return "skip"

    if fit_score >= 80 and company.tier <= 2:
        return "apply_now"
    if fit_score >= 70 and company.tier == 1 and company.warm_path:
        return "apply_now"
    if fit_score >= 65:
        return "consider"
    if fit_score >= 50 and company.tier <= 2:
        return "stretch"
    return "skip"


def _technical_blockers(title_lower: str) -> list[HardBlocker]:
    if any(term in title_lower for term in TECHNICAL_ENGINEERING_TERMS) or (
        "engineer" in title_lower and "strategist" not in title_lower
    ):
        return [
            HardBlocker(
                type="technical_role",
                evidence=(
                    "Posting centers on production engineering or forward-deployed "
                    "engineering."
                ),
            )
        ]
    return []


def _is_stretch_family(title: str, department: str, text: str) -> bool:
    combined = f"{title} {department}".lower()
    return _matches_any(combined, STRETCH_FAMILY_PATTERNS) or _matches_any(
        text,
        STRETCH_FAMILY_PATTERNS,
    )


def _role_text(row: sqlite3.Row) -> str:
    return f"{row['title']} {row['department'] or ''} {row['description_text']}".lower()


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _matches_target_location(locations: list[str], target_locations: list[str]) -> bool:
    haystack = " ".join(locations).lower()
    for raw_location in target_locations:
        for candidate in re.split(r"[/;]", raw_location.lower()):
            candidate = candidate.strip()
            if candidate and candidate in haystack:
                return True
    return False


def _config_version(file_name: str, fallback: str) -> str:
    path = Path(__file__).resolve().parents[2] / "config" / file_name
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("version:"):
                return line.split(":", 1)[1].strip().strip('"')
    except OSError:
        pass
    return fallback


def _alignments(title: str, text: str) -> list[Alignment]:
    alignments = [
        Alignment(
            job_requirement="Lead ambiguous strategy and operations work.",
            candidate_evidence=(
                "Google Devices & Services strategy/operations background with global "
                "rollout and transformation programs."
            ),
            evidence_strength=(
                "strong"
                if re.search("strategy|operations|deployment", text)
                else "medium"
            ),
        ),
        Alignment(
            job_requirement="Partner with technical and business stakeholders.",
            candidate_evidence=(
                "Zenith product work included BRDs, validation logic, Engineering "
                "partnership, UAT, training, and rollout."
            ),
            evidence_strength="strong",
        ),
    ]
    if "deployment strategist" in title.lower():
        alignments.append(
            Alignment(
                job_requirement="Bridge customer problems into deployable technical solutions.",
                candidate_evidence=(
                    "Claims-validation and Fitbit migration work show business problem "
                    "framing through implementation."
                ),
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
                mitigation=(
                    "Do not pursue unless the posting is actually strategy-led rather "
                    "than engineering-led."
                ),
            )
        ]
    gaps = [
        Gap(
            gap=(
                "Direct external customer value-scoping is a stretch versus the "
                "candidate's internal product/operations background."
            ),
            severity="medium",
            mitigation=(
                "Anchor the story in Zenith requirements, Engineering partnership, "
                "UAT, rollout, and measurable impact."
            ),
        )
    ]
    if "technical" in text or "architecture" in text:
        gaps.append(
            Gap(
                gap="Technical depth may be tested.",
                severity="medium",
                mitigation=(
                    "Prepare a clear boundary: business/product logic and implementation "
                    "leadership, not production coding."
                ),
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
    return (
        f"{title} scores {fit_score}/100 with recommendation `{recommendation}` under "
        "the Checkpoint B deterministic evaluator."
    )
