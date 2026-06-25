"""Structured development evaluator for Checkpoint B.

This is intentionally deterministic. It validates the data path and mirrors the
required evaluation schema, but it is not the final LLM-backed evaluator.
"""

from __future__ import annotations

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
from app.services.llm_evaluator import (
    LLMProvider,
    LLMRoleRequest,
    ModelSpendTracker,
    PROMPT_VERSION,
    provider_from_env,
)
from app.services.material import material_hash_for_row


DETERMINISTIC_FALLBACK_VERSION = "deterministic_fallback_v1"
HYBRID_EVALUATOR_VERSION = "hybrid_claude_v1"


@dataclass(frozen=True)
class RelevanceDecision:
    should_evaluate: bool
    reason: str


def input_hash(row: sqlite3.Row) -> str:
    return material_hash_for_row(row)


def should_evaluate(row: sqlite3.Row, company: CompanyConfig) -> bool:
    """Compatibility wrapper around the logged relevance decision."""

    return relevance_decision(row, company).should_evaluate


def relevance_decision(row: sqlite3.Row, company: CompanyConfig) -> RelevanceDecision:
    """Cost-bound LLM evaluation without judging fit from full JD text."""

    filter_config = load_relevance_filter()
    profile = load_candidate_profile()
    location_policy = load_location_policy()
    if filter_config.target_location_required:
        location_decision = _location_gate_decision(row, company, location_policy)
        if location_decision is not None:
            return location_decision

    role_family_patterns = (
        profile.primary_role_family_patterns + profile.stretch_role_family_patterns
    )
    title_department = _title_department_text(row)
    if _matches_any(title_department, role_family_patterns):
        return RelevanceDecision(True, "matched_title_department_role_family")

    if _matches_any(title_department, filter_config.excluded_title_department_patterns):
        return RelevanceDecision(False, "excluded_title_department_function")

    return RelevanceDecision(True, "ambiguous_title_department_routed_to_llm")


def evaluate_role(
    row: sqlite3.Row,
    company: CompanyConfig,
    *,
    llm_provider: LLMProvider | None = None,
    spend_tracker: ModelSpendTracker | None = None,
) -> RoleEvaluation:
    title = row["title"]
    title_lower = row["title"].lower()
    text = _role_text(row)
    locations = json.loads(row["locations_json"])
    scoring_policy = load_scoring_policy()
    location_policy = load_location_policy()
    profile = load_candidate_profile()
    hard_blockers = _hard_blockers(
        title_lower,
        text,
        locations,
        company,
        scoring_policy,
        location_policy,
        profile,
    )
    provider = llm_provider or provider_from_env()
    if provider is not None:
        tracker = spend_tracker or ModelSpendTracker.from_env()
        tracker.assert_budget_allows()
        llm_result = provider.evaluate(LLMRoleRequest(row=row, company=company, profile=profile))
        tracker.record(llm_result.cost_usd)
        llm_hard_blockers = [
            HardBlocker(type=item.type, evidence=item.evidence)
            for item in llm_result.output.hard_blockers
        ]
        return _role_evaluation_from_llm(
            row,
            company,
            _merge_hard_blockers(hard_blockers, llm_hard_blockers),
            llm_result.output.dimensions,
            llm_confidence=llm_result.output.confidence,
            llm_alignments=[
                Alignment(
                    job_requirement=item.job_requirement,
                    candidate_evidence=item.candidate_evidence,
                    evidence_strength=item.evidence_strength,
                )
                for item in llm_result.output.alignments
            ],
            llm_gaps=[
                Gap(gap=item.gap, severity=item.severity, mitigation=item.mitigation)
                for item in llm_result.output.gaps
            ],
            llm_uncertainties=list(llm_result.output.uncertainties),
            llm_summary=llm_result.output.summary,
            llm_advisory_recommendation=llm_result.output.advisory_recommendation,
            model_version=llm_result.model_version,
            prompt_version=llm_result.prompt_version,
            cache_hit=llm_result.cache_hit,
            scoring_policy=scoring_policy,
            location_policy=location_policy,
            profile=profile,
        )

    role_family_fit = _role_family_fit(title, row["department"] or "", text, profile)
    evidence_strength = _evidence_strength(text, profile)
    scope_seniority = _scope_seniority(title, text, company, profile)
    gap_manageability = 35 if hard_blockers else _gap_manageability(text, scoring_policy)

    dimensions = {
        "role_family_fit": role_family_fit,
        "evidence_strength": evidence_strength,
        "scope_seniority": scope_seniority,
        "gap_manageability": gap_manageability,
    }
    fit_score = _weighted_fit_score(dimensions, scoring_policy)
    feasibility_state, feasibility_reason = _feasibility(locations, location_policy)
    recommendation = _final_recommendation(
        row,
        company,
        hard_blockers,
        fit_score,
        feasibility_state,
        scoring_policy,
        profile,
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
            else f"Tier {company.tier} company from the configured watchlist.",
        },
        recommendation=recommendation,
        hard_blockers=hard_blockers,
        alignments=_alignments(title, text, profile),
        gaps=_gaps(text, hard_blockers),
        uncertainties=[
            (
                f"No ANTHROPIC_API_KEY was configured, so this evaluation uses "
                f"{DETERMINISTIC_FALLBACK_VERSION}."
            ),
            "Work authorization must be confirmed against the stored policy before applying.",
        ],
        provenance={
            "candidate_profile_version": profile.version,
            "location_policy_version": location_policy.version,
            "scoring_policy_version": scoring_policy.version,
            "prompt_version": "deterministic_fallback",
            "model_version": DETERMINISTIC_FALLBACK_VERSION,
            "evaluator_version": DETERMINISTIC_FALLBACK_VERSION,
            "fallback_quality": "true",
            "fallback_reason": "missing_anthropic_api_key",
        },
        summary=_summary(title, fit_score, recommendation, hard_blockers),
    )


def _role_evaluation_from_llm(
    row: sqlite3.Row,
    company: CompanyConfig,
    hard_blockers: list[HardBlocker],
    dimensions: dict[str, int],
    *,
    llm_confidence: float,
    llm_alignments: list[Alignment],
    llm_gaps: list[Gap],
    llm_uncertainties: list[str],
    llm_summary: str,
    llm_advisory_recommendation: str,
    model_version: str,
    prompt_version: str,
    cache_hit: bool,
    scoring_policy: ScoringPolicyConfig,
    location_policy: LocationPolicyConfig,
    profile: CandidateProfileConfig,
) -> RoleEvaluation:
    locations = json.loads(row["locations_json"])
    fit_score = _weighted_fit_score(dimensions, scoring_policy)
    feasibility_state, feasibility_reason = _feasibility(locations, location_policy)
    recommendation = _final_recommendation(
        row,
        company,
        hard_blockers,
        fit_score,
        feasibility_state,
        scoring_policy,
        profile,
    )
    gaps = list(llm_gaps)
    if hard_blockers:
        gaps = _gaps(_role_text(row), hard_blockers) + gaps
    return RoleEvaluation(
        role_fit_score=fit_score,
        confidence=llm_confidence,
        dimensions=dimensions,
        feasibility={
            "state": "blocked" if hard_blockers else feasibility_state,
            "reason": "Hard blocker overrides feasibility."
            if hard_blockers
            else feasibility_reason,
            "policy_version": location_policy.version,
        },
        strategic_priority=_strategic_priority(company),
        recommendation=recommendation,
        hard_blockers=hard_blockers,
        alignments=llm_alignments,
        gaps=gaps,
        uncertainties=llm_uncertainties,
        provenance={
            "candidate_profile_version": profile.version,
            "location_policy_version": location_policy.version,
            "scoring_policy_version": scoring_policy.version,
            "prompt_version": prompt_version or PROMPT_VERSION,
            "model_version": model_version,
            "evaluator_version": HYBRID_EVALUATOR_VERSION,
            "fallback_quality": "false",
            "llm_advisory_recommendation": llm_advisory_recommendation,
            "llm_cache_hit": str(cache_hit).lower(),
        },
        summary=llm_summary,
    )


def _strategic_priority(company: CompanyConfig) -> dict[str, str | bool]:
    return {
        "company_tier": f"tier_{company.tier}",
        "freshness": "new_today",
        "warm_path": company.warm_path,
        "reason": "Tier 1 company with a warm path in the tracker."
        if company.warm_path
        else f"Tier {company.tier} company from the configured watchlist.",
    }


def _final_recommendation(
    row: sqlite3.Row,
    company: CompanyConfig,
    hard_blockers: list[HardBlocker],
    fit_score: int,
    feasibility_state: str,
    scoring_policy: ScoringPolicyConfig,
    profile: CandidateProfileConfig,
) -> str:
    return _recommendation(
        fit_score,
        feasibility_state,
        company,
        hard_blockers,
        overleveled=_is_overleveled_role(
            row["title"],
            _role_text(row),
            company,
            profile,
        ),
        stretch_family=_is_stretch_family(
            row["title"],
            row["department"] or "",
            _role_text(row),
            profile,
        ),
        scoring_policy=scoring_policy,
    )


def _role_family_fit(
    title: str,
    department: str,
    text: str,
    profile: CandidateProfileConfig | None = None,
) -> int:
    profile = profile or load_candidate_profile()
    combined = f"{title} {department}".lower()
    title_lower = title.lower()
    if _is_customer_success_function(combined):
        return 35
    if _is_junior_scope_title(title_lower) and not _has_clear_senior_scope(text, profile):
        return 15
    if _is_plain_revenue_ops_manager(title_lower):
        return 30
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


def _evidence_strength(
    text: str,
    profile: CandidateProfileConfig | None = None,
) -> int:
    profile = profile or load_candidate_profile()
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
    if _language_match(text, profile):
        score += 4
    return min(score, 88)


def _scope_seniority(
    title: str,
    text: str,
    company: CompanyConfig | None = None,
    profile: CandidateProfileConfig | None = None,
) -> int:
    profile = profile or load_candidate_profile()
    title_lower = title.lower()
    if _is_overleveled_role(title, text, company, profile):
        return 38
    if any(term in title_lower for term in profile.below_level_title_terms):
        return 35
    if _is_plain_revenue_ops_manager(title_lower) and not _has_clear_senior_scope(text, profile):
        return 50
    if "analyst" in title_lower and not _has_clear_senior_scope(text, profile):
        return 42
    if "associate" in title_lower and not _has_clear_senior_scope(text, profile):
        return 42
    score = 68
    if any(term in title_lower for term in profile.senior_title_terms):
        score += 10
    if _has_clear_senior_scope(text, profile):
        score += 6
    return min(score, 88)


def _gap_manageability(
    text: str,
    scoring_policy: ScoringPolicyConfig | None = None,
) -> int:
    scoring_policy = scoring_policy or load_scoring_policy()
    penalties = scoring_policy.gap_penalties
    score = 78
    leading_text = text[:160]
    if _is_junior_scope_title(leading_text):
        score -= penalties.get("junior_scope_title", 0)
    if _is_plain_revenue_ops_manager(leading_text):
        score -= penalties.get("plain_revenue_ops", 0)
    if _is_customer_success_function(text):
        score -= penalties.get("customer_success", 0)
    if "python" in text or "sql" in text:
        score -= penalties.get("python_or_sql", 0)
    if "technical" in text or "architecture" in text:
        score -= penalties.get("technical_or_architecture", 0)
    if _technical_pm_depth("", text):
        score -= penalties.get("technical_pm_depth", 0)
    if _partnership_domain_gap(text):
        score -= penalties.get("partnership_domain_gap", 0)
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
    authorization = market.current_authorization.lower()
    if "blocked" in authorization or "impossible" in authorization:
        return "blocked", market.notes
    if "not_authorized" in authorization or "high_friction" in authorization:
        return "sponsorship_required", market.notes
    if market.expected_availability_date:
        return (
            "viable",
            f"{market.notes} Expected availability: {market.expected_availability_date}.",
        )
    if "authorized" in authorization or "viable" in authorization:
        return "viable", market.notes
    if market.sponsorship_required:
        return "sponsorship_required", market.notes
    return "uncertain", market.notes


def _market_for_location(
    joined_location: str,
    location_policy: LocationPolicyConfig,
) -> MarketPolicyConfig | None:
    market_aliases = {
        "Australia": ("sydney", "melbourne", "australia"),
        "UK": ("london", "united kingdom", "uk"),
        "Singapore": ("singapore",),
        "EU": ("germany", "munich", "berlin", "paris", "amsterdam", "madrid", "europe"),
    }
    us_market = location_policy.markets.get("United States")
    if us_market and _matches_us_location(joined_location):
        return us_market
    for market_name, aliases in market_aliases.items():
        market = location_policy.markets.get(market_name)
        if market and any(alias in joined_location for alias in aliases):
            return market
    return None


def _matches_us_location(joined_location: str) -> bool:
    if (
        re.search(r"\b(?:united states|california|new york|san francisco|san mateo)\b", joined_location)
        or "(us)" in joined_location
    ):
        return True
    # Glendale exists outside the US, so only use it when the location also
    # carries an explicit US/California signal.
    return bool(
        re.search(r"\bglendale\b", joined_location)
        and re.search(r"\b(?:california|ca)\b|\(us\)", joined_location)
    )


def _recommendation(
    fit_score: int,
    feasibility_state: str,
    company: CompanyConfig,
    hard_blockers: list[HardBlocker],
    *,
    overleveled: bool = False,
    stretch_family: bool = False,
    exceptional_upside: bool = False,
    scoring_policy: ScoringPolicyConfig | None = None,
) -> str:
    scoring_policy = scoring_policy or load_scoring_policy()
    thresholds = scoring_policy.recommendation_thresholds
    if hard_blockers or feasibility_state == "blocked":
        return "blocked"
    if overleveled:
        return "skip"
    if company.tier >= 3:
        if company.warm_path and fit_score >= thresholds.stretch_min_fit:
            return "stretch"
        return "skip"

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


def _hard_blockers(
    title_lower: str,
    text: str,
    locations: list[str],
    company: CompanyConfig,
    scoring_policy: ScoringPolicyConfig,
    location_policy: LocationPolicyConfig,
    profile: CandidateProfileConfig,
) -> list[HardBlocker]:
    blockers = list(_technical_blockers(title_lower, scoring_policy))
    blockers.extend(_disqualifying_hard_requirements(text, profile))
    if _technical_pm_depth(title_lower, text):
        blockers.append(
            HardBlocker(
                type="technical_pm_depth",
                evidence=(
                    "Role is a native product-management lane with technical/product "
                    "specification depth beyond the candidate's current anchor."
                ),
            )
        )
    if _security_clearance_required(text):
        blockers.append(
            HardBlocker(
                type="security_clearance",
                evidence=(
                    "Posting appears to require government/security clearance that "
                    "the candidate should not assume they can satisfy."
                ),
            )
        )
    work_authorization = _work_authorization_blocker(locations, company, location_policy)
    if work_authorization is not None:
        blockers.append(work_authorization)
    return blockers


def _merge_hard_blockers(
    base: list[HardBlocker],
    additional: list[HardBlocker],
) -> list[HardBlocker]:
    seen = {(blocker.type, blocker.evidence) for blocker in base}
    merged = list(base)
    for blocker in additional:
        key = (blocker.type, blocker.evidence)
        if key not in seen:
            merged.append(blocker)
            seen.add(key)
    return merged


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


def _work_authorization_blocker(
    locations: list[str],
    company: CompanyConfig,
    location_policy: LocationPolicyConfig,
) -> HardBlocker | None:
    joined = " ".join(locations).lower()
    market = _market_for_location(joined, location_policy)
    if market is None or company.warm_path:
        return None
    authorization = market.current_authorization.lower()
    if market.sponsorship_required and (
        "not_authorized" in authorization or "high_friction" in authorization
    ):
        return HardBlocker(
            type="location_work_authorization",
            evidence=(
                f"{market.name} role requires a credible sponsorship, transfer, or "
                "warm-route path under the stored location policy."
            ),
        )
    return None


def _disqualifying_hard_requirements(
    text: str,
    profile: CandidateProfileConfig,
) -> list[HardBlocker]:
    config = profile.disqualifying_hard_requirements
    if not config.requirement_patterns:
        return []
    blockers: list[HardBlocker] = []
    for fragment in _requirement_fragments(text):
        if _matches_any(fragment, config.nice_to_have_context_patterns):
            continue
        if not _matches_any(fragment, config.must_have_context_patterns):
            continue
        if not _matches_any(fragment, config.requirement_patterns):
            continue
        blockers.append(
            HardBlocker(
                type="disqualifying_hard_requirement",
                evidence=(
                    "Required technical credential/depth appears outside the "
                    f"candidate profile: {fragment.strip()}"
                ),
            )
        )
    return blockers


def _requirement_fragments(text: str) -> list[str]:
    return [
        fragment.strip()
        for fragment in re.split(r"[\n.;•]+", text)
        if fragment.strip()
    ]


def _security_clearance_required(text: str) -> bool:
    return bool(
        re.search(
            (
                r"\b(?:security|sc|dv)\s+clearance\b"
                r"|\bsecurity vetting\b"
                r"|\bsecurity check\s*\(sc\)"
                r"|developed vetting"
                r"|continuous (?:uk )?residency"
            ),
            text,
            flags=re.IGNORECASE,
        )
    )


def _technical_pm_depth(title_lower: str, text: str) -> bool:
    leading_text = text[:160]
    if title_lower:
        is_product_manager = "product manager" in title_lower
    else:
        is_product_manager = "product manager" in leading_text
    if not is_product_manager:
        return False
    depth_signals = (
        "product management experience",
        "technical specifications",
        "implementation details",
        "engage with engineering",
        "engineering to design",
        "experimentation",
        "a/b testing",
        "sdlc",
    )
    return sum(1 for signal in depth_signals if signal in text) >= 2


def _is_customer_success_function(text: str) -> bool:
    return bool(
        re.search(
            r"\bcustomer success\b|\baccount management\b|\brenewals?\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def _is_junior_scope_title(title_lower: str) -> bool:
    return "analyst" in title_lower or "associate" in title_lower


def _is_plain_revenue_ops_manager(title_lower: str) -> bool:
    return (
        "revenue operations" in title_lower
        and "strategy" not in title_lower
        and "senior" not in title_lower
        and "lead" not in title_lower
    )


def _has_clear_senior_scope(
    text: str,
    profile: CandidateProfileConfig,
) -> bool:
    if not any(term in text for term in profile.scope_signals):
        return False
    return bool(
        re.search(
            (
                r"\bown(?:s|ing)?\b.{0,80}\b(?:program|strategy|roadmap|portfolio|workstream)\b"
                r"|\bdrive\b.{0,80}\b(?:executive|cross-functional|strategic|program|transformation)\b"
                r"|\bexecutive\b.{0,80}\b(?:rhythm|stakeholder|leadership|reporting)\b"
                r"|\blead\b.{0,80}\b(?:cross-functional|strategic|program|transformation)\b"
                r"|\bcross-functional\b.{0,80}\b(?:leadership|strategy|program|execution)\b"
            ),
            text,
            flags=re.IGNORECASE,
        )
    )


def _is_overleveled_role(
    title: str,
    text: str,
    company: CompanyConfig | None,
    profile: CandidateProfileConfig,
) -> bool:
    title_lower = title.lower()
    if not _matches_any(title_lower, profile.seniority_ceiling.over_level_title_patterns):
        return False
    if "chief of staff" in title_lower:
        return False
    exception_text = f"{title} {company.name if company else ''} {text}".lower()
    return not _matches_any(
        exception_text,
        profile.seniority_ceiling.startup_exception_patterns,
    )


def _partnership_domain_gap(text: str) -> bool:
    return bool(
        re.search(
            r"\bglobal partnerships?\b|\bcard networks?\b|\bbanking\b",
            text,
            flags=re.IGNORECASE,
        )
    )


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


def _title_department_text(row: sqlite3.Row) -> str:
    return f"{row['title']} {row['department'] or ''}".lower()


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _location_gate_decision(
    row: sqlite3.Row,
    company: CompanyConfig,
    location_policy: LocationPolicyConfig,
) -> RelevanceDecision | None:
    gate = location_policy.pre_evaluation_filter
    if not gate.enabled:
        locations = json.loads(row["locations_json"])
        if not _matches_target_location(locations, company.target_locations):
            return RelevanceDecision(False, "non_target_location")
        return None

    locations_text = " ".join(json.loads(row["locations_json"])).lower()
    if not locations_text.strip():
        return RelevanceDecision(False, "location_filter_missing_location")

    if _matches_any(locations_text, gate.allowed_location_patterns):
        return None

    if _matches_any(locations_text, gate.tier1_only_location_patterns):
        if company.tier == 1:
            return None
        return RelevanceDecision(False, "location_filter_tier1_only_location")

    if _matches_any(locations_text, gate.us_location_patterns):
        role_text = _role_text(row)
        title_department = _title_department_text(row)
        if (
            company.tier == 1
            and _matches_any(role_text, gate.us_sponsorship_patterns)
            and _matches_any(title_department, gate.us_exceptional_role_patterns)
        ):
            return None
        return RelevanceDecision(
            False,
            "location_filter_us_requires_tier1_sponsorship_exceptional_role",
        )

    if _matches_any(locations_text, gate.skipped_location_patterns):
        return RelevanceDecision(False, "location_filter_skipped_market")

    return RelevanceDecision(False, "location_filter_not_allowed")


def _matches_target_location(locations: list[str], target_locations: list[str]) -> bool:
    haystack = " ".join(locations).lower()
    for raw_location in target_locations:
        for candidate in re.split(r"[/;]", raw_location.lower()):
            candidate = candidate.strip()
            if candidate and candidate in haystack:
                return True
    return False


def _alignments(
    title: str,
    text: str,
    profile: CandidateProfileConfig | None = None,
) -> list[Alignment]:
    profile = profile or load_candidate_profile()
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
    language_match = _language_match(text, profile)
    if language_match:
        language, proficiency = language_match
        alignments.append(
            Alignment(
                job_requirement=f"Operate in a {language}-language role context.",
                candidate_evidence=f"{language} is listed in the profile as {proficiency}.",
                evidence_strength="strong",
            )
        )
    return alignments


def _gaps(text: str, hard_blockers: list[HardBlocker]) -> list[Gap]:
    if hard_blockers:
        blocker_types = ", ".join(blocker.type for blocker in hard_blockers)
        return [
            Gap(
                gap=f"Hard blocker detected: {blocker_types}.",
                severity="high",
                mitigation=(
                    "Do not pursue unless the blocker is disproven by current source "
                    "or owner context."
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
        blocker_types = ", ".join(blocker.type for blocker in hard_blockers)
        return f"{title} is blocked because of: {blocker_types}."
    return (
        f"{title} scores {fit_score}/100 with recommendation `{recommendation}` under "
        "the Checkpoint B deterministic evaluator."
    )


def _language_match(
    text: str,
    profile: CandidateProfileConfig,
) -> tuple[str, str] | None:
    for language, proficiency in profile.languages.items():
        if language.lower() == "english":
            continue
        if not _is_profile_language_strength_usable(proficiency):
            continue
        for pattern in _language_requirement_patterns(language):
            if re.search(pattern, text, flags=re.IGNORECASE):
                return language, proficiency
    return None


def _is_profile_language_strength_usable(proficiency: str) -> bool:
    normalized = proficiency.lower()
    return any(term in normalized for term in ("native", "professional", "fluent"))


def _language_requirement_patterns(language: str) -> tuple[str, ...]:
    normalized = language.lower().strip()
    language_pattern = r"\s+".join(re.escape(part) for part in normalized.split())
    patterns = [
        rf"\b{language_pattern}[-\s]+speaking\b",
        rf"\bfluent\s+(?:in\s+)?{language_pattern}\b",
        rf"\b{language_pattern}\s+required\b",
        rf"\brequires?\s+{language_pattern}\b",
        rf"\b{language_pattern}\s+language\b",
        rf"\b(?:native|professional|business)\s+{language_pattern}\b",
        rf"\bproficiency\s+in\s+{language_pattern}\b",
    ]
    if normalized == "german":
        patterns.append(r"\bdeutsch\b")
    return tuple(patterns)
