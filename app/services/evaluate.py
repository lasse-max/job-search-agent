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

from app.config import (
    CandidateProfileConfig,
    LocationPolicyConfig,
    MarketPolicyConfig,
    ScoringPolicyConfig,
    load_candidate_profile,
    load_location_policy,
    load_relevance_filter,
    load_scoring_policy,
)
from app.models import Alignment, CompanyConfig, Gap, HardBlocker, RoleEvaluation


EVALUATOR_VERSION = "uncalibrated_dev_stub_v1"


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
    profile = load_candidate_profile()
    locations = json.loads(row["locations_json"])
    if filter_config.target_location_required and not _matches_target_location(
        locations,
        company.target_locations,
    ):
        return RelevanceDecision(False, "non_target_location")

    text = _role_text(row)
    role_family_patterns = (
        profile.primary_role_family_patterns + profile.stretch_role_family_patterns
    )
    if not _matches_any(text, role_family_patterns):
        return RelevanceDecision(False, "no_primary_or_stretch_family_signal")

    return RelevanceDecision(True, "matched_target_location_and_role_family")


def evaluate_role(row: sqlite3.Row, company: CompanyConfig) -> RoleEvaluation:
    title = row["title"]
    title_lower = row["title"].lower()
    text = _role_text(row)
    locations = json.loads(row["locations_json"])
    scoring_policy = load_scoring_policy()
    location_policy = load_location_policy()
    profile = load_candidate_profile()
    hard_blockers = _technical_blockers(title_lower, scoring_policy)

    role_family_fit = _role_family_fit(title, row["department"] or "", text, profile)
    evidence_strength = _evidence_strength(text)
    scope_seniority = _scope_seniority(title, text, profile)
    gap_manageability = 35 if hard_blockers else _gap_manageability(text, scoring_policy)

    dimensions = {
        "role_family_fit": role_family_fit,
        "evidence_strength": evidence_strength,
        "scope_seniority": scope_seniority,
        "gap_manageability": gap_manageability,
    }
    fit_score = _weighted_fit_score(dimensions, scoring_policy)
    feasibility_state, feasibility_reason = _feasibility(locations, location_policy)
    is_stretch = _is_stretch_family(title, row["department"] or "", text, profile)
    recommendation = _recommendation(
        fit_score,
        feasibility_state,
        company,
        hard_blockers,
        stretch_family=is_stretch,
        scoring_policy=scoring_policy,
    )

    return RoleEvaluation(
        role_fit_score=fit_score,
        confidence=0.68,
        dimensions=dimensions,
        feasibility={
            "state": "blocked" if hard_blockers else feasibility_state,
            "reason": "Technical blocker overrides feasibility."
            if hard_blockers
            else feasibility_reason,
            "policy_version": location_policy.version,
        },
        strategic_priority={
            "company_tier": f"tier_{company.tier}",
            "freshness": "new_today",
            "warm_path": company.warm_path,
            "reason": "Tier 1 company with a warm path in the tracker."
            if company.warm_path
            else _strategic_priority_reason(company, profile),
        },
        recommendation=recommendation,
        hard_blockers=hard_blockers,
        alignments=_alignments(title, text),
        gaps=_gaps(text, hard_blockers),
        uncertainties=[
            f"This Checkpoint B evaluation uses {EVALUATOR_VERSION}, not the final LLM evaluator.",
            "Work authorization must be confirmed against the stored policy before applying.",
        ],
        provenance={
            "candidate_profile_version": profile.version,
            "location_policy_version": location_policy.version,
            "scoring_policy_version": scoring_policy.version,
            "evaluator_version": EVALUATOR_VERSION,
        },
        summary=_summary(title, fit_score, recommendation, hard_blockers),
    )


def _role_family_fit(
    title: str,
    department: str,
    text: str,
    profile: CandidateProfileConfig | None = None,
) -> int:
    profile = profile or load_candidate_profile()
    combined = f"{title} {department}".lower()
    if _is_stretch_family(title, department, text, profile):
        return 78
    if _matches_any(combined, profile.primary_role_family_patterns) or _matches_any(
        text,
        profile.primary_role_family_patterns,
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


def _scope_seniority(
    title: str,
    text: str,
    profile: CandidateProfileConfig | None = None,
) -> int:
    profile = profile or load_candidate_profile()
    title_lower = title.lower()
    if any(term in title_lower for term in profile.below_level_title_terms):
        return 35
    score = 68
    if any(term in title_lower for term in profile.senior_title_terms):
        score += 10
    if any(term in text for term in profile.scope_signals):
        score += 6
    return min(score, 88)


def _gap_manageability(
    text: str,
    scoring_policy: ScoringPolicyConfig | None = None,
) -> int:
    scoring_policy = scoring_policy or load_scoring_policy()
    penalties = scoring_policy.gap_penalties
    score = 78
    if "python" in text or "sql" in text:
        score -= penalties.get("python_or_sql", 0)
    if "technical" in text or "architecture" in text:
        score -= penalties.get("technical_or_architecture", 0)
    if "quota" in text:
        score -= penalties.get("quota", 0)
    return max(score, 45)


def _weighted_fit_score(
    dimensions: dict[str, int],
    scoring_policy: ScoringPolicyConfig | None = None,
) -> int:
    scoring_policy = scoring_policy or load_scoring_policy()
    return round(
        sum(
            dimensions[dimension] * weight
            for dimension, weight in scoring_policy.fit_weights.items()
        )
    )


def _feasibility(
    locations: list[str],
    location_policy: LocationPolicyConfig | None = None,
) -> tuple[str, str]:
    location_policy = location_policy or load_location_policy()
    joined = " ".join(locations).lower()
    market = _market_for_location(joined, location_policy)
    if market is None:
        return (
            "uncertain",
            "Location is not explicitly mapped by the active location policy.",
        )
    if market.name == "United States":
        return "sponsorship_required", market.notes
    if "blocked" in market.current_authorization:
        return "blocked", market.notes
    if market.expected_availability_date:
        return (
            "viable",
            f"{market.notes} Expected availability: {market.expected_availability_date}.",
        )
    return "viable", market.notes


def _market_for_location(
    joined_location: str,
    location_policy: LocationPolicyConfig,
) -> MarketPolicyConfig | None:
    market_aliases = {
        "Australia": ("sydney", "melbourne", "australia"),
        "UK": ("london", "united kingdom", "uk"),
        "Singapore": ("singapore",),
        "United States": ("united states", "california", "new york", "san francisco"),
        "EU": ("germany", "munich", "berlin", "paris", "amsterdam", "madrid", "europe"),
    }
    for market_name, aliases in market_aliases.items():
        market = location_policy.markets.get(market_name)
        if market and any(alias in joined_location for alias in aliases):
            return market
    return None


def _recommendation(
    fit_score: int,
    feasibility_state: str,
    company: CompanyConfig,
    hard_blockers: list[HardBlocker],
    *,
    stretch_family: bool = False,
    exceptional_upside: bool = False,
    scoring_policy: ScoringPolicyConfig | None = None,
) -> str:
    scoring_policy = scoring_policy or load_scoring_policy()
    thresholds = scoring_policy.recommendation_thresholds
    if hard_blockers or feasibility_state == "blocked":
        return "blocked"

    if stretch_family:
        if (
            fit_score >= thresholds.warm_path_apply_now_min_fit
            and company.tier == thresholds.stretch_apply_now_tier
            and (company.warm_path or exceptional_upside)
        ):
            return "apply_now"
        if fit_score >= thresholds.consider_min_fit:
            return "consider"
        if (
            fit_score >= thresholds.stretch_min_fit
            and company.tier <= thresholds.max_stretch_tier
        ):
            return "stretch"
        return "skip"

    if (
        fit_score >= thresholds.apply_now_min_fit
        and company.tier <= thresholds.max_apply_now_tier
    ):
        return "apply_now"
    if (
        fit_score >= thresholds.warm_path_apply_now_min_fit
        and company.tier == thresholds.warm_path_apply_now_tier
        and company.warm_path
    ):
        return "apply_now"
    if fit_score >= thresholds.consider_min_fit:
        return "consider"
    if (
        fit_score >= thresholds.stretch_min_fit
        and company.tier <= thresholds.max_stretch_tier
    ):
        return "stretch"
    return "skip"


def _technical_blockers(
    title_lower: str,
    scoring_policy: ScoringPolicyConfig | None = None,
) -> list[HardBlocker]:
    scoring_policy = scoring_policy or load_scoring_policy()
    allowed = any(
        term in title_lower for term in scoring_policy.technical_blocker_allowed_terms
    )
    if any(term in title_lower for term in scoring_policy.technical_blocker_terms) or (
        "engineer" in title_lower and not allowed
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


def _is_stretch_family(
    title: str,
    department: str,
    text: str,
    profile: CandidateProfileConfig | None = None,
) -> bool:
    profile = profile or load_candidate_profile()
    combined = f"{title} {department}".lower()
    return _matches_any(combined, profile.stretch_role_family_patterns) or _matches_any(
        text,
        profile.stretch_role_family_patterns,
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


def _strategic_priority_reason(company: CompanyConfig, profile: CandidateProfileConfig) -> str:
    brand_rule = str(profile.brand_floor.get("rule") or "")
    if brand_rule:
        return f"Tier {company.tier} company from the configured watchlist. {brand_rule}"
    return f"Tier {company.tier} company from the configured watchlist."


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
