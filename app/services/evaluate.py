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
    LLMProviderError,
    LLMRoleRequest,
    ModelSpendTracker,
    PROMPT_VERSION,
    provider_from_env,
)
from app.services.material import material_hash_for_row
from app.services.text_rules import unsupported_language_requirement


DETERMINISTIC_FALLBACK_VERSION = "deterministic_fallback_v1"
HYBRID_EVALUATOR_VERSION = "hybrid_claude_v3"


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
    if _employer_opt_out_reason(company, profile):
        return RelevanceDecision(False, "employer_opt_out")
    location_policy = load_location_policy()
    if filter_config.target_location_required:
        location_decision = _location_gate_decision(row, company, location_policy)
        if location_decision is not None:
            return location_decision

    role_family_patterns = (
        profile.primary_role_family_patterns + profile.stretch_role_family_patterns
    )
    title_department = _title_department_text(row)
    requirement_text = _role_requirement_text(row)
    if unsupported_language_requirement(requirement_text, profile.languages):
        return RelevanceDecision(False, "unsupported_language_requirement")

    if _government_defense_or_clearance_scope(requirement_text):
        return RelevanceDecision(False, "government_defense_clearance_declined")

    if _matches_any(title_department, filter_config.excluded_title_department_patterns):
        return RelevanceDecision(False, "excluded_title_department_function")

    if _matches_any(title_department, role_family_patterns):
        return RelevanceDecision(True, "matched_title_department_role_family")

    return RelevanceDecision(True, "ambiguous_title_department_routed_to_llm")


def evaluate_role(
    row: sqlite3.Row,
    company: CompanyConfig,
    *,
    llm_provider: LLMProvider | None = None,
    spend_tracker: ModelSpendTracker | None = None,
    use_env_provider: bool = True,
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
    provider = llm_provider or (provider_from_env() if use_env_provider else None)
    if provider is not None:
        tracker = spend_tracker or ModelSpendTracker.from_env()
        tracker.assert_budget_allows()
        try:
            llm_result = provider.evaluate(
                LLMRoleRequest(row=row, company=company, profile=profile)
            )
        except LLMProviderError as exc:
            tracker.record(exc.cost_usd)
            raise
        tracker.record(llm_result.cost_usd)
        llm_hard_blockers = [
            HardBlocker(type=item.type, evidence=item.evidence)
            for item in llm_result.output.hard_blockers
        ]
        return _role_evaluation_from_llm(
            row,
            company,
            _merge_hard_blockers(
                hard_blockers,
                _filter_llm_hard_blockers(llm_hard_blockers, profile),
            ),
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
            estimated_level=llm_result.output.estimated_level,
            level_confidence=llm_result.output.level_confidence,
            level_rationale=llm_result.output.level_rationale,
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

    dimensions = _apply_fit_inputs(
        row,
        company,
        {
            "role_family_fit": role_family_fit,
            "evidence_strength": evidence_strength,
            "scope_seniority": scope_seniority,
            "gap_manageability": gap_manageability,
        },
        scoring_policy,
        location_policy,
        profile,
    )
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
    estimated_level: str,
    level_confidence: int,
    level_rationale: str,
    model_version: str,
    prompt_version: str,
    cache_hit: bool,
    scoring_policy: ScoringPolicyConfig,
    location_policy: LocationPolicyConfig,
    profile: CandidateProfileConfig,
) -> RoleEvaluation:
    locations = json.loads(row["locations_json"])
    calibrated_dimensions = _calibrated_llm_dimensions(
        row,
        dimensions,
        company,
        scoring_policy,
        location_policy,
        profile,
        estimated_level=estimated_level,
        level_confidence=level_confidence,
    )
    fit_score = _weighted_fit_score(calibrated_dimensions, scoring_policy)
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
        dimensions=calibrated_dimensions,
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
        estimated_level=estimated_level,
        level_confidence=level_confidence,
        level_rationale=level_rationale,
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
        stretch_family=_is_stretch_family(
            row["title"],
            row["department"] or "",
            _role_text(row),
            profile,
        ),
        surface_capped=_is_low_priority_surface_function(
            row["title"],
            row["department"] or "",
            _role_text(row),
            profile,
        ),
        scoring_policy=scoring_policy,
    )


def _calibrated_llm_dimensions(
    row: sqlite3.Row,
    dimensions: dict[str, int],
    company: CompanyConfig,
    scoring_policy: ScoringPolicyConfig,
    location_policy: LocationPolicyConfig,
    profile: CandidateProfileConfig,
    *,
    estimated_level: str,
    level_confidence: int,
) -> dict[str, int]:
    """Apply conservative calibration floors to LLM scores.

    Claude Haiku is useful for comparing responsibilities, but on the labelled
    set it underrates obvious target-family title/department matches. These
    floors keep the model's relative judgment while preventing core S&O/BizOps
    roles from falling below the digest surface solely because of conservative
    evidence scoring.
    """

    calibrated = {dimension: int(score) for dimension, score in dimensions.items()}
    title = row["title"]
    title_lower = title.lower()
    title_department = _title_department_text(row)
    if (
        _matches_any(title_department, profile.primary_role_family_patterns)
        and not _is_plain_revenue_ops_manager(title_lower)
    ):
        floors = {
            "role_family_fit": 82,
            "evidence_strength": 62,
            "scope_seniority": 70,
            "gap_manageability": 65,
        }
        for dimension, floor in floors.items():
            calibrated[dimension] = max(calibrated[dimension], floor)
    elif _is_stretch_family(title, row["department"] or "", _role_text(row), profile):
        floors = {
            "role_family_fit": 78,
            "evidence_strength": 66,
            "scope_seniority": 68,
            "gap_manageability": 68,
        }
        for dimension, floor in floors.items():
            calibrated[dimension] = max(calibrated[dimension], floor)
    fit_adjusted = _apply_fit_inputs(
        row,
        company,
        calibrated,
        scoring_policy,
        location_policy,
        profile,
    )
    return _apply_estimated_level_fit(
        fit_adjusted,
        estimated_level=estimated_level,
        level_confidence=level_confidence,
        scoring_policy=scoring_policy,
    )


def _apply_estimated_level_fit(
    dimensions: dict[str, int],
    *,
    estimated_level: str,
    level_confidence: int,
    scoring_policy: ScoringPolicyConfig,
) -> dict[str, int]:
    """Modestly sort out-of-band levels without suppressing an otherwise surfaced role."""

    if level_confidence < 50 or estimated_level in {"L4", "L5", "unknown"}:
        return dimensions
    penalty_key = {
        "L3": "level_below_target_scope",
        "L6": "level_one_band_scope",
        "L7+": "level_two_plus_bands_scope",
    }.get(estimated_level)
    if penalty_key is None:
        return dimensions
    penalty = scoring_policy.gap_penalties.get(penalty_key, 0)
    adjusted = dict(dimensions)
    adjusted["scope_seniority"] = _clamp_score(
        adjusted.get("scope_seniority", 0) - penalty
    )
    baseline_fit = _weighted_fit_score(dimensions, scoring_policy)
    adjusted_fit = _weighted_fit_score(adjusted, scoring_policy)
    if (
        baseline_fit >= scoring_policy.recommendation_thresholds.stretch_min_fit
        and adjusted_fit < scoring_policy.recommendation_thresholds.stretch_min_fit
    ):
        return dimensions
    return adjusted


def _apply_fit_inputs(
    row: sqlite3.Row,
    company: CompanyConfig,
    dimensions: dict[str, int],
    scoring_policy: ScoringPolicyConfig,
    location_policy: LocationPolicyConfig,
    profile: CandidateProfileConfig,
) -> dict[str, int]:
    adjusted = {dimension: int(score) for dimension, score in dimensions.items()}
    text = _role_text(row)
    fit_cap = _fit_cap_for_gate(row, company, text, location_policy, profile)
    if fit_cap is not None:
        for dimension in adjusted:
            adjusted[dimension] = min(adjusted[dimension], fit_cap)
    if _is_low_priority_surface_function(
        row["title"],
        row["department"] or "",
        text,
        profile,
    ):
        adjusted["role_family_fit"] = min(adjusted.get("role_family_fit", 0), 58)
        adjusted["evidence_strength"] = min(adjusted.get("evidence_strength", 0), 58)
        adjusted["scope_seniority"] = min(adjusted.get("scope_seniority", 0), 58)
        adjusted["gap_manageability"] = min(adjusted.get("gap_manageability", 0), 58)
    if _partnership_domain_gap(_title_department_text(row)):
        for dimension in adjusted:
            adjusted[dimension] = min(adjusted[dimension], 68)
    if _required_credential_gap(text):
        penalty = scoring_policy.gap_penalties.get("required_credential", 22)
        for dimension in adjusted:
            adjusted[dimension] = min(adjusted[dimension], 68)
        adjusted["gap_manageability"] = adjusted.get("gap_manageability", 0) - penalty
    if company.warm_path:
        adjusted["evidence_strength"] = adjusted.get("evidence_strength", 0) + 3
        adjusted["gap_manageability"] = adjusted.get("gap_manageability", 0) + 3
    if company.tier == 1:
        adjusted["evidence_strength"] = adjusted.get("evidence_strength", 0) + 2
    elif company.tier >= 3:
        adjusted["evidence_strength"] = adjusted.get("evidence_strength", 0) - 18
        adjusted["gap_manageability"] = adjusted.get("gap_manageability", 0) - 18
    return {dimension: _clamp_score(score) for dimension, score in adjusted.items()}


def _fit_cap_for_gate(
    row: sqlite3.Row,
    company: CompanyConfig,
    text: str,
    location_policy: LocationPolicyConfig,
    profile: CandidateProfileConfig,
) -> int | None:
    title = str(row["title"])
    title_lower = title.lower()
    title_department = _title_department_text(row)
    requirement_text = _role_requirement_text(row)
    filter_config = load_relevance_filter()

    if _employer_opt_out_reason(company, profile):
        return 55

    if filter_config.target_location_required:
        location_decision = _location_gate_decision(row, company, location_policy)
        warm_us_exception = (
            company.warm_path
            and location_decision is not None
            and location_decision.reason
            == "location_filter_us_requires_tier1_sponsorship_exceptional_role"
        )
        if location_decision is not None and not warm_us_exception:
            return 55
    locations = json.loads(row["locations_json"])
    if _work_authorization_blocker(locations, company, location_policy) is not None:
        return 55
    if unsupported_language_requirement(requirement_text, profile.languages):
        return 55
    if _government_defense_or_clearance_scope(requirement_text):
        return 55
    if _matches_any(title_department, filter_config.excluded_title_department_patterns):
        return 55
    if _agent_development_product_manager(title_department):
        return 68
    if _off_function_title_department(title_department):
        return 55
    if _technical_pm_depth(title_lower, text):
        return 55
    if _security_clearance_required(text):
        return 55

    return None


def _clamp_score(value: int) -> int:
    return max(0, min(100, int(value)))


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
        "Australia": ("sydney", "melbourne", "perth", "australia"),
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
    stretch_family: bool = False,
    exceptional_upside: bool = False,
    surface_capped: bool = False,
    scoring_policy: ScoringPolicyConfig | None = None,
) -> str:
    scoring_policy = scoring_policy or load_scoring_policy()
    thresholds = scoring_policy.recommendation_thresholds
    if hard_blockers or feasibility_state == "blocked":
        return "blocked"
    if fit_score >= thresholds.apply_now_min_fit:
        return "apply_now"
    if fit_score >= thresholds.consider_min_fit:
        return "consider"
    if fit_score >= thresholds.stretch_min_fit:
        return "stretch"
    return "skip"


def _is_low_priority_surface_function(
    title: str,
    department: str,
    text: str,
    profile: CandidateProfileConfig,
) -> bool:
    title_lower = title.lower()
    title_department = f"{title} {department}".lower()
    requirement_text = _requirement_scope_text(title_department, text)
    if unsupported_language_requirement(requirement_text, profile.languages):
        return True
    if _government_defense_or_clearance_scope(requirement_text):
        return True
    if _pre_sales_value_function(title_department):
        return True
    if _adjacent_ops_noise(title_department):
        return True
    if _off_function_title_department(title_department):
        return True
    if _is_plain_revenue_ops_manager(title_lower):
        return True
    if _is_stretch_family(title, department, text, profile) and re.search(
        r"\b(?:government|public sector|defen[cs]e)\b",
        title_department,
        flags=re.IGNORECASE,
    ):
        return True
    if re.search(
        (
            r"\btechnical account management\b"
            r"|\btechnical account manager\b"
            r"|\bsupport\s*&\s*services\b"
            r"|\bproposals?\s*(?:&|and)\s*assurance\b"
            r"|\bassurance manager\b"
            r"|\bstrategic finance\b"
            r"|\bfinance technology\b"
            r"|\bcorporate development\b"
            r"|\bstrategic pricing\b"
            r"|\bchannel sales\b"
            r"|\btalent acquisition\b"
            r"|\blegal\b"
            r"|\brisk,\s*ethics\b"
            r"|\bethics,\s*advocacy\b"
        ),
        title_department,
        flags=re.IGNORECASE,
    ):
        return True
    return False


def _off_function_title_department(text: str) -> bool:
    if _native_product_manager_function(text):
        return True
    if _partnership_manager_without_strategy_ops(text):
        return True
    if re.search(
        (
            r"\bproduct marketing\b"
            r"|\bmarketing\b"
            r"|\bgrowth marketing\b"
            r"|\bbrand\b.{0,40}\bmarketing\b"
            r"|\bcommercial market (?:specialist|manager)\b"
            r"|\bpricing\s*&\s*yield\b"
            r"|\byield management\b"
            r"|\baccount executive\b"
            r"|\baccount manager\b"
            r"|\bcustomer success\b"
            r"|\b(?:sales|business) development representative\b"
            r"|\b(?:sdr|bdr)\b"
            r"|\brecruit(?:er|ing)\b"
        ),
        text,
        flags=re.IGNORECASE,
    ):
        return True
    return False


def _native_product_manager_function(text: str) -> bool:
    if not re.search(r"\bproduct manager\b", text, flags=re.IGNORECASE):
        return False
    if _agent_development_product_manager(text):
        return False
    return not re.search(
        (
            r"\bproduct operations\b"
            r"|\bproduct ops\b"
            r"|\bproduct strateg\w*\b"
            r"|\bproduct\b.{0,80}\b(?:moneti[sz]ation|pricing)\b"
            r"|\b(?:moneti[sz]ation|pricing)\b.{0,80}\bproduct\b"
        ),
        text,
        flags=re.IGNORECASE,
    )


def _agent_development_product_manager(text: str) -> bool:
    return bool(
        re.search(r"\bproduct manager\b", text, flags=re.IGNORECASE)
        and re.search(r"\bagent development\b", text, flags=re.IGNORECASE)
    )


def _partnership_manager_without_strategy_ops(text: str) -> bool:
    if not re.search(
        r"\b(?:partner|partnerships?)\b.{0,60}\bmanager\b|\bmanager\b.{0,60}\b(?:partner|partnerships?)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return False
    return not re.search(
        r"\b(?:strategy|strategic operations|operations|bizops|program|gtm|go-to-market)\b",
        text,
        flags=re.IGNORECASE,
    )


def _government_defense_or_clearance_scope(text: str) -> bool:
    if re.search(
        r"\b(?:security|sc|dv)\s+clearance\b|\bsecurity vetting\b",
        text,
        flags=re.IGNORECASE,
    ):
        return True
    for fragment in _requirement_fragments(text):
        if re.search(
            r"\b(?:government|public sector|military|national security)\b",
            fragment,
            flags=re.IGNORECASE,
        ):
            return True
        if not re.search(r"\bdefen[cs]e\b", fragment, flags=re.IGNORECASE):
            continue
        if re.search(r"\b(?:first|second|third)?\s*line of defen[cs]e\b", fragment):
            continue
        if _nice_to_have_context(fragment):
            continue
        return True
    return False


def _nice_to_have_context(text: str) -> bool:
    return bool(
        re.search(
            (
                r"\bpreferred\b"
                r"|\bnice to have\b"
                r"|\ba plus\b"
                r"|\bplus\b"
                r"|\bbonus\b"
                r"|\basset\b"
                r"|\bnot required\b"
                r"|\boptional\b"
                r"|\bhelpful\b"
                r"|\bdesirable\b"
            ),
            text,
            flags=re.IGNORECASE,
        )
    )


def _pre_sales_value_function(text: str) -> bool:
    return bool(
        re.search(
            (
                r"\bpre[-\s]?sales\b"
                r"|\bvalue engineering\b"
                r"|\bvalue engineer\b"
                r"|\bvalue partner\b"
                r"|\bsolutions? engineer\b"
                r"|\bsolution engineering\b"
                r"|\bsales engineering\b"
            ),
            text,
            flags=re.IGNORECASE,
        )
    )


def _adjacent_ops_noise(text: str) -> bool:
    return bool(
        re.search(
            (
                r"\blogistics\b"
                r"|\bsupply[-\s]?chain\b.{0,80}\bstandards?\b"
                r"|\bstandards?\b.{0,80}\bsupply[-\s]?chain\b"
                r"|\bsafety\b.{0,80}\breadiness\b"
                r"|\boperations safety\b"
                r"|\brisk\b.{0,80}\boperations\b"
                r"|\bcompliance\b.{0,80}\boperations\b"
                r"|\boperations\b.{0,80}\b(?:risk|compliance)\b"
                r"|\bproposals?\s*(?:&|and)\s*assurance\b"
                r"|\bintegration manager\b"
            ),
            text,
            flags=re.IGNORECASE,
        )
    )


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
    blockers.extend(
        _disqualifying_hard_requirements(
            text,
            profile,
        )
    )
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


def _filter_llm_hard_blockers(
    blockers: list[HardBlocker],
    profile: CandidateProfileConfig,
) -> list[HardBlocker]:
    return [
        blocker
        for blocker in blockers
        if _llm_hard_blocker_is_enforceable(
            blocker,
            profile,
        )
    ]


def _llm_hard_blocker_is_enforceable(
    blocker: HardBlocker,
    profile: CandidateProfileConfig,
) -> bool:
    if blocker.type != "disqualifying_hard_requirement":
        return True
    return has_disqualifying_hard_requirement(blocker.evidence, profile)


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
    return [
        HardBlocker(
            type="disqualifying_hard_requirement",
            evidence=(
                "Required technical credential/depth appears outside the "
                f"candidate profile: {fragment.strip()}"
            ),
        )
        for fragment in _enforceable_disqualifying_fragments(text, profile)
    ]


def has_disqualifying_hard_requirement(
    text: str,
    profile: CandidateProfileConfig | None = None,
) -> bool:
    """Return whether text contains an enforceable profile-level hard requirement."""

    return bool(
        _enforceable_disqualifying_fragments(
            text,
            profile or load_candidate_profile(),
        )
    )


def _enforceable_disqualifying_fragments(
    text: str,
    profile: CandidateProfileConfig,
) -> list[str]:
    config = profile.disqualifying_hard_requirements
    if not config.requirement_patterns:
        return []
    fragments: list[str] = []
    for fragment in _requirement_fragments(text):
        if _matches_any(fragment, config.nice_to_have_context_patterns):
            continue
        if not _matches_any(fragment, config.requirement_patterns):
            continue
        if _technical_degree_mention(fragment):
            if not _degree_requirement(fragment) or not _matches_any(
                fragment,
                config.must_have_context_patterns,
            ):
                continue
        elif not _technical_depth_requirement(fragment):
            continue
        fragments.append(fragment)
    return fragments


def _degree_requirement(text: str) -> bool:
    if not _technical_degree_mention(text):
        return False
    has_nontechnical_field = bool(
        re.search(
            r"\b(?:business|economics|finance|management|commerce|strategy|operations|"
            r"social sciences?|liberal arts)\b",
            text,
            flags=re.IGNORECASE,
        )
    )
    has_alternative_list = bool(re.search(r"\b(?:or|and/or)\b|[,/]", text, re.IGNORECASE))
    return not (has_nontechnical_field and has_alternative_list)


def _technical_degree_mention(text: str) -> bool:
    return bool(
        re.search(
            (
                r"\b(?:degree|bachelor'?s?|master'?s?|msc|bs|ba)\b"
                r".{0,100}\b(?:computer science|software engineering|engineering)\b"
                r"|\b(?:computer science|software engineering|engineering)\b"
                r".{0,100}\b(?:degree|bachelor'?s?|master'?s?|msc|bs|ba)\b"
            ),
            text,
            flags=re.IGNORECASE,
        )
    )


def _technical_depth_requirement(text: str) -> bool:
    technical_signal = (
        r"(?:\b(?:advanced|expert|professional|proficient|strong)\b.{0,50}"
        r"\b(?:python|java|typescript|javascript|programming|coding|software development)\b"
        r"|\bproduction software (?:development|engineering)\b"
        r"|\bproduction coding\b"
        r"|\b(?:build|building|built|develop|developing|write|writing)\b.{0,50}"
        r"\bproduction (?:software|code)\b"
        r"|\b(?:deep|strong|expert|advanced)\b.{0,50}"
        r"\b(?:machine learning|ml|data science)\b.{0,50}"
        r"\b(?:engineering|model(?:l)?ing)\b"
        r"|\bml engineering\b"
        r"|\bproficient\b.{0,50}\b(?:developing|writing|building)\b.{0,25}\bcode\b"
        r"|\bhands[- ]on(?: experience)?\b.{0,80}"
        r"\b(?:building|developing|deploying)\b.{0,80}"
        r"\b(?:ai applications?|software|code)\b)"
    )
    for sentence in re.split(r"[\n.;•]+", text):
        sentence = sentence.strip()
        match = re.search(technical_signal, sentence, flags=re.IGNORECASE)
        if not match:
            continue
        candidate_owned = (
            r"\byou(?:'ll|\s+will|\s+must|\s+need\s+to|\s+are expected to|"
            r"\s+are required to)?\s+(?:are\s+)?(?:proficient|expert|strong)\b"
            r".{0,60}\b(?:python|java|typescript|javascript|programming|coding|"
            r"software development)\b"
            r"|\byou(?:'ll|\s+will|\s+must|\s+need\s+to|\s+are expected to|"
            r"\s+are required to)?\s+(?:design|build|develop|write|ship|own)\b"
            r".{0,100}\b(?:production (?:software|code)|ai applications?|"
            r"(?:deep\s+)?(?:machine learning|ml) engineering)\b"
        )
        if re.search(candidate_owned, sentence, flags=re.IGNORECASE):
            return True
        direct_context = (
            rf"\b(?:this|the) role\b.{{0,30}}"
            rf"\b(?:requires?|owns?|involves?|includes?|will|must|needs?\s+to)\b"
            rf".{{0,70}}{technical_signal}"
            rf"|\b(?:responsible for|ability to|expected to|required to)\b.{{0,100}}"
            rf"{technical_signal}"
            rf"|\b(?:requirements?|qualifications?|mandatory|must[- ]have)\b.{{0,100}}"
            rf"{technical_signal}"
            rf"|\b(?:hands[- ]on experience|experience|proficiency)\b.{{0,100}}"
            rf"{technical_signal}"
            rf"|{technical_signal}.{{0,80}}\b(?:required|mandatory|must[- ]have|experience|"
            r"proficiency|central duty|core duty|primary responsibility)\b"
        )
        if re.search(direct_context, sentence, flags=re.IGNORECASE):
            return True
        if match.start() <= 12 and not re.search(
            r"^(?:at\s+\w+|our\s+|the\s+(?:platform|product|company|team)|we\s+)",
            sentence,
            flags=re.IGNORECASE,
        ):
            return True
    return False


def _required_credential_gap(text: str) -> bool:
    config = load_candidate_profile().disqualifying_hard_requirements
    credential_pattern = (
        r"\b(?:pmp|project management professional|certificat(?:e|ion)|certified|credential)\b"
        r"|\b(?:intermediate|advanced|professional|proficient)\b.{0,80}"
        r"\b(?:platform|tool|system|software|cloud)\b"
    )
    for fragment in _requirement_fragments(text):
        if _matches_any(fragment, config.nice_to_have_context_patterns):
            continue
        if not _matches_any(fragment, config.must_have_context_patterns):
            continue
        if re.search(credential_pattern, fragment, flags=re.IGNORECASE):
            return True
    return False


def _requirement_fragments(text: str) -> list[str]:
    fragments: list[str] = []
    for sentence in re.split(r"[\n.;•]+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        fragments.extend(_preference_scoped_fragments(sentence))
    return fragments


def _preference_scoped_fragments(sentence: str) -> list[str]:
    preference_pattern = (
        r"\b(?:preferred|nice to have|bonus|a plus|asset|optional|helpful|desirable|"
        r"not required)\b"
    )
    if not re.search(preference_pattern, sentence, flags=re.IGNORECASE):
        return [sentence]
    required_context_pattern = (
        r"\b(?:required?|mandatory|must|needs?\s+to|minimum qualifications?|"
        r"requirements?|qualifications?)\b"
    )
    if not re.search(required_context_pattern, sentence, flags=re.IGNORECASE) and re.search(
        rf"{preference_pattern}\s*$",
        sentence,
        flags=re.IGNORECASE,
    ):
        return [f"preferred: {sentence}"]

    delimiter_pattern = re.compile(
        r"(?P<delimiter>\s*,\s*(?:(?:and|but|while|whereas|with)\s+)?"
        r"|\s+(?:and|but|while|whereas|with)\s+)",
        flags=re.IGNORECASE,
    )
    tokens = delimiter_pattern.split(sentence)
    parts: list[str] = []
    buffer = tokens[0].strip()
    inherited_preference = False
    for index in range(1, len(tokens), 2):
        delimiter = tokens[index]
        right = tokens[index + 1].strip()
        buffer_preferred = bool(
            re.search(preference_pattern, buffer, flags=re.IGNORECASE)
        ) or inherited_preference
        right_preferred = bool(
            re.search(preference_pattern, right, flags=re.IGNORECASE)
        )
        if not (buffer_preferred or right_preferred):
            buffer = _join_requirement_clause(buffer, right, delimiter)
            continue

        if buffer:
            parts.append(buffer)
        delimiter_lower = delimiter.casefold()
        right_required = bool(
            re.search(
                required_context_pattern,
                right,
                flags=re.IGNORECASE,
            )
        )
        inherited_preference = (
            buffer_preferred
            and not right_preferred
            and not right_required
            and not any(
                word in delimiter_lower for word in ("but", "while", "whereas")
            )
        )
        buffer = f"preferred: {right}" if inherited_preference else right
    if buffer:
        parts.append(buffer)
    return parts


def _join_requirement_clause(buffer: str, clause: str, delimiter: str) -> str:
    if not clause:
        return buffer
    if not buffer:
        return clause
    connector = delimiter.strip() or ","
    return f"{buffer} {connector} {clause}".strip()


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


def _employer_opt_out_reason(
    company: CompanyConfig,
    profile: CandidateProfileConfig,
) -> str | None:
    company_name = re.sub(r"\s+", " ", company.name).strip().casefold()
    for configured_name, reason in profile.employer_opt_outs.items():
        if company_name == re.sub(r"\s+", " ", configured_name).strip().casefold():
            return reason
    return None


def _compensation_seniority_signal(title: str, text: str) -> str | None:
    max_compensation = _max_annual_compensation(text)
    if max_compensation is None:
        return None
    currency, amount = max_compensation
    thresholds = {
        "usd": 250_000,
        "eur": 220_000,
        "gbp": 180_000,
        "aud": 300_000,
        "sgd": 300_000,
    }
    threshold = thresholds.get(currency)
    if threshold is None or amount < threshold:
        return None
    title_lower = title.lower()
    if re.search(r"\b(?:lead|principal|staff)\b", title_lower) and not re.search(
        r"\b(?:head of|director|vp|vice president|chief)\b",
        title_lower,
    ):
        return "over_target_senior_ic"
    return "over_target_executive"


def _max_annual_compensation(text: str) -> tuple[str, int] | None:
    candidates: list[tuple[str, int]] = []
    for fragment in _requirement_fragments(text):
        for span in _compensation_spans(fragment):
            currency = _compensation_currency(span)
            if currency is None:
                continue
            amounts = [
                _parse_compensation_amount(match.group("amount"), match.group("suffix"))
                for match in re.finditer(
                    r"(?P<amount>\d[\d,.]*)(?:\s*(?P<suffix>k))?",
                    span,
                    flags=re.IGNORECASE,
                )
            ]
            amounts = [amount for amount in amounts if amount >= 20_000]
            if amounts:
                candidates.append((currency, max(amounts)))
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate[1])


def _compensation_spans(fragment: str) -> list[str]:
    context = (
        r"\b(?:salary|compensation|base pay|pay range|annual(?:ly)?|per annum|p\.a\.|"
        r"per year|ote)\b"
    )
    currency = (
        r"(?:[$€£]|\b(?:usd|eur|gbp|aud|sgd|us dollars?|euros?|pounds?"
        r"|australian dollars?|singapore dollars?)\b)"
    )
    amount = r"\d[\d,.]*(?:\s*k)?"
    amount_or_range = (
        rf"(?:{currency}\s*)?{amount}"
        rf"(?:\s*(?:-|–|—|to)\s*(?:{currency}\s*)?{amount})?"
        rf"(?:\s*{currency})?"
    )
    patterns = [
        rf"{context}[^.;\n]{{0,90}}?{amount_or_range}",
        rf"{amount_or_range}[^.;\n]{{0,45}}?{context}",
    ]
    spans: list[str] = []
    seen: set[tuple[int, int]] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, fragment, flags=re.IGNORECASE):
            bounds = match.span()
            if bounds in seen:
                continue
            seen.add(bounds)
            span = match.group(0).strip()
            if _compensation_currency(span) is not None:
                spans.append(span)
    return spans


def _compensation_currency(text: str) -> str | None:
    lowered = text.lower()
    if "$" in text or "usd" in lowered or "us dollar" in lowered:
        return "usd"
    if "€" in text or "eur" in lowered or "euro" in lowered:
        return "eur"
    if "£" in text or "gbp" in lowered or "pound" in lowered:
        return "gbp"
    if "aud" in lowered or "australian dollar" in lowered:
        return "aud"
    if "sgd" in lowered or "singapore dollar" in lowered:
        return "sgd"
    return None


def _parse_compensation_amount(raw: str, suffix: str | None) -> int:
    cleaned = raw.strip()
    if "," in cleaned:
        normalized = cleaned.replace(",", "")
    elif "." in cleaned and len(cleaned.rsplit(".", 1)[-1]) == 3:
        normalized = cleaned.replace(".", "")
    else:
        normalized = cleaned
    amount = float(normalized)
    if suffix:
        amount *= 1_000
    return int(amount)


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


def _role_requirement_text(row: sqlite3.Row) -> str:
    return _requirement_scope_text(
        _title_department_text(row),
        str(row["description_text"] or "").lower(),
    )


def _requirement_scope_text(title_department: str, description_text: str) -> str:
    if _looks_like_aggregate_careers_page(description_text):
        return title_department
    return f"{title_department}\n{description_text}".lower()


def _looks_like_aggregate_careers_page(text: str) -> bool:
    lower = text.lower()
    if "allfilters" in lower or ("all jobs" in lower and "positions" in lower):
        return True
    if "open roles" not in lower:
        return False
    role_list_markers = re.findall(
        (
            r"\bsoftware engineer\b"
            r"|\bproduct manager\b"
            r"|\bsales engineer\b"
            r"|\brecruiter\b"
            r"|\baccount executive\b"
            r"|\bstrategist,\s*agent development\b"
            r"|\bdepartment all departments\b"
        ),
        lower,
    )
    return len(role_list_markers) >= 4


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
    if _required_credential_gap(text):
        gaps.append(
            Gap(
                gap="Required credential or platform certification is not in the candidate profile.",
                severity="medium",
                mitigation=(
                    "Down-rank unless the credential is easy to obtain before applying "
                    "or owner context confirms it is not a true requirement."
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
