"""Configuration helpers for the first vertical slice."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.models import CompanyConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_DB_PATH = DATA_DIR / "job_search_agent.sqlite"


@dataclass(frozen=True)
class RelevanceFilterConfig:
    version: str
    target_location_required: bool
    excluded_title_department_patterns: tuple[str, ...]


@dataclass(frozen=True)
class RecommendationThresholds:
    apply_now_min_fit: int
    warm_path_apply_now_min_fit: int
    consider_min_fit: int
    stretch_min_fit: int
    max_apply_now_tier: int
    max_stretch_tier: int
    warm_path_apply_now_tier: int
    stretch_apply_now_tier: int


@dataclass(frozen=True)
class ScoringPolicyConfig:
    version: str
    fit_weights: dict[str, float]
    recommendation_thresholds: RecommendationThresholds
    digest_limits: dict[str, int]
    true_blockers: tuple[str, ...]
    technical_blocker_terms: tuple[str, ...]
    technical_blocker_allowed_terms: tuple[str, ...]
    strong_penalties: tuple[str, ...]
    gap_penalties: dict[str, int]


@dataclass(frozen=True)
class MarketPolicyConfig:
    name: str
    current_authorization: str
    sponsorship_required: bool
    expected_availability_date: str | None
    confidence: str
    notes: str


@dataclass(frozen=True)
class LocationGateConfig:
    enabled: bool
    allowed_location_patterns: tuple[str, ...]
    tier1_only_location_patterns: tuple[str, ...]
    skipped_location_patterns: tuple[str, ...]
    us_location_patterns: tuple[str, ...]
    us_sponsorship_patterns: tuple[str, ...]
    us_exceptional_role_patterns: tuple[str, ...]


@dataclass(frozen=True)
class LocationPolicyConfig:
    version: str
    markets: dict[str, MarketPolicyConfig]
    pre_evaluation_filter: LocationGateConfig


@dataclass(frozen=True)
class HardRequirementConfig:
    must_have_context_patterns: tuple[str, ...]
    nice_to_have_context_patterns: tuple[str, ...]
    requirement_patterns: tuple[str, ...]


@dataclass(frozen=True)
class SeniorityCeilingConfig:
    over_level_title_patterns: tuple[str, ...]
    startup_exception_patterns: tuple[str, ...]


@dataclass(frozen=True)
class CandidateProfileConfig:
    version: str
    positioning: str
    primary_role_families: tuple[str, ...]
    approved_stretch_families: tuple[str, ...]
    primary_role_family_patterns: tuple[str, ...]
    stretch_role_family_patterns: tuple[str, ...]
    below_level_title_terms: tuple[str, ...]
    senior_title_terms: tuple[str, ...]
    scope_signals: tuple[str, ...]
    seniority_ceiling: SeniorityCeilingConfig
    languages: dict[str, str]
    brand_floor: dict[str, object]
    disqualifying_hard_requirements: HardRequirementConfig
    usually_deprioritize: tuple[str, ...]
    honest_gaps: tuple[str, ...]


def _parse_scalar(value: str) -> object:
    value = value.strip()
    if value == "null":
        return None
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        return ast.literal_eval(value)
    if value.startswith('"') and value.endswith('"'):
        return ast.literal_eval(value)
    try:
        return int(value)
    except ValueError:
        return value


def load_watchlist(path: Path = CONFIG_DIR / "watchlist.yaml") -> list[dict[str, object]]:
    """Load company blocks from the generated Stage 0 watchlist file."""

    companies: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line.startswith("  - name: "):
            if current is not None:
                companies.append(current)
            current = {"name": _parse_scalar(line.split(": ", 1)[1])}
            continue
        if current is None or not line.startswith("    ") or ": " not in line:
            continue
        key, value = line.strip().split(": ", 1)
        current[key] = _parse_scalar(value)

    if current is not None:
        companies.append(current)

    return companies


def load_company_config(company_name: str = "Databricks") -> CompanyConfig:
    """Return one enabled company config from the watchlist."""

    for company in load_watchlist():
        if company.get("name") == company_name:
            source_key = company.get("source_key")
            if not isinstance(source_key, str) or not source_key:
                raise ValueError(f"{company_name} does not have a configured source_key")
            return CompanyConfig(
                name=str(company["name"]),
                tier=int(company["tier"]),
                enabled=bool(company["enabled"]),
                ats_type=str(company["ats_type"]),
                source_key=source_key,
                careers_url=str(company["careers_url"]),
                target_locations=list(company.get("target_locations", [])),
                target_role_family_notes=str(company.get("target_role_family_notes", "")),
                warm_path=bool(company.get("warm_path", False)),
                expected_volume_min=_expected_volume_min(company.get("job_count_at_audit")),
            )
    raise ValueError(f"Company not found in watchlist: {company_name}")


def load_enabled_company_configs() -> list[CompanyConfig]:
    return [
        load_company_config(str(company["name"]))
        for company in load_watchlist()
        if bool(company.get("enabled"))
    ]


@lru_cache(maxsize=1)
def load_scoring_policy(
    path: Path = CONFIG_DIR / "scoring_policy.yaml",
) -> ScoringPolicyConfig:
    data = _read_yaml_mapping(path)
    raw_weights = data.get("fit_dimensions")
    if not isinstance(raw_weights, dict):
        raise ValueError(f"No fit_dimensions configured in {path}")

    weights: dict[str, float] = {}
    for name, raw_dimension in raw_weights.items():
        if not isinstance(raw_dimension, dict):
            continue
        weight = raw_dimension.get("weight")
        if not isinstance(weight, int | float):
            raise ValueError(f"Invalid weight for {name} in {path}")
        weights[str(name)] = float(weight) / 100

    thresholds = data.get("recommendation_thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError(f"No recommendation_thresholds configured in {path}")

    return ScoringPolicyConfig(
        version=str(data.get("version") or "scoring_policy_unknown"),
        fit_weights=weights,
        recommendation_thresholds=RecommendationThresholds(
            apply_now_min_fit=_int_threshold(thresholds, "apply_now_min_fit"),
            warm_path_apply_now_min_fit=_int_threshold(
                thresholds,
                "warm_path_apply_now_min_fit",
            ),
            consider_min_fit=_int_threshold(thresholds, "consider_min_fit"),
            stretch_min_fit=_int_threshold(thresholds, "stretch_min_fit"),
            max_apply_now_tier=_int_threshold(thresholds, "max_apply_now_tier"),
            max_stretch_tier=_int_threshold(thresholds, "max_stretch_tier"),
            warm_path_apply_now_tier=_int_threshold(
                thresholds,
                "warm_path_apply_now_tier",
            ),
            stretch_apply_now_tier=_int_threshold(thresholds, "stretch_apply_now_tier"),
        ),
        digest_limits=_dict_of_int(data.get("digest_limits")),
        true_blockers=_tuple_of_str(data.get("true_blockers")),
        technical_blocker_terms=_tuple_of_str(data.get("technical_blocker_terms")),
        technical_blocker_allowed_terms=_tuple_of_str(
            data.get("technical_blocker_allowed_terms"),
        ),
        strong_penalties=_tuple_of_str(data.get("strong_penalties")),
        gap_penalties=_dict_of_int(data.get("gap_penalties")),
    )


@lru_cache(maxsize=1)
def load_location_policy(
    path: Path = CONFIG_DIR / "location_policy.yaml",
) -> LocationPolicyConfig:
    data = _read_yaml_mapping(path)
    raw_markets = data.get("markets")
    if not isinstance(raw_markets, dict):
        raise ValueError(f"No markets configured in {path}")

    markets: dict[str, MarketPolicyConfig] = {}
    for name, raw_market in raw_markets.items():
        if not isinstance(raw_market, dict):
            raise ValueError(f"Invalid market policy for {name} in {path}")
        markets[str(name)] = MarketPolicyConfig(
            name=str(name),
            current_authorization=str(raw_market.get("current_authorization") or ""),
            sponsorship_required=bool(raw_market.get("sponsorship_required")),
            expected_availability_date=_optional_str(
                raw_market.get("expected_availability_date"),
            ),
            confidence=str(raw_market.get("confidence") or ""),
            notes=str(raw_market.get("notes") or ""),
        )

    raw_gate = data.get("pre_evaluation_filter")
    if not isinstance(raw_gate, dict):
        raw_gate = {}

    return LocationPolicyConfig(
        version=str(data.get("version") or "location_policy_unknown"),
        markets=markets,
        pre_evaluation_filter=LocationGateConfig(
            enabled=bool(raw_gate.get("enabled", True)),
            allowed_location_patterns=_tuple_of_str(raw_gate.get("allowed_location_patterns")),
            tier1_only_location_patterns=_tuple_of_str(
                raw_gate.get("tier1_only_location_patterns"),
            ),
            skipped_location_patterns=_tuple_of_str(raw_gate.get("skipped_location_patterns")),
            us_location_patterns=_tuple_of_str(raw_gate.get("us_location_patterns")),
            us_sponsorship_patterns=_tuple_of_str(raw_gate.get("us_sponsorship_patterns")),
            us_exceptional_role_patterns=_tuple_of_str(
                raw_gate.get("us_exceptional_role_patterns"),
            ),
        ),
    )


@lru_cache(maxsize=1)
def load_candidate_profile(
    path: Path = CONFIG_DIR / "candidate_profile.yaml",
) -> CandidateProfileConfig:
    data = _read_yaml_mapping(path)
    role_patterns = data.get("role_family_patterns")
    if not isinstance(role_patterns, dict):
        raise ValueError(f"No role_family_patterns configured in {path}")
    scope_signals = data.get("scope_seniority_signals")
    if not isinstance(scope_signals, dict):
        raise ValueError(f"No scope_seniority_signals configured in {path}")
    target_seniority = data.get("target_seniority")
    if not isinstance(target_seniority, dict):
        target_seniority = {}
    seniority_ceiling = target_seniority.get("seniority_ceiling")
    if not isinstance(seniority_ceiling, dict):
        seniority_ceiling = {}

    brand_floor = data.get("brand_floor")
    if not isinstance(brand_floor, dict):
        brand_floor = {}
    languages = data.get("languages")
    if not isinstance(languages, dict):
        languages = {}
    hard_requirements = data.get("disqualifying_hard_requirements")
    if not isinstance(hard_requirements, dict):
        hard_requirements = {}

    return CandidateProfileConfig(
        version=str(data.get("version") or "candidate_profile_unknown"),
        positioning=str(data.get("positioning") or ""),
        primary_role_families=_tuple_of_str(data.get("primary_role_families")),
        approved_stretch_families=_tuple_of_str(data.get("approved_stretch_families")),
        primary_role_family_patterns=_tuple_of_str(role_patterns.get("primary")),
        stretch_role_family_patterns=_tuple_of_str(role_patterns.get("stretch")),
        below_level_title_terms=_tuple_of_str(scope_signals.get("below_level_title_terms")),
        senior_title_terms=_tuple_of_str(scope_signals.get("senior_title_terms")),
        scope_signals=_tuple_of_str(scope_signals.get("scope_signals")),
        seniority_ceiling=SeniorityCeilingConfig(
            over_level_title_patterns=_tuple_of_str(
                seniority_ceiling.get("over_level_title_patterns"),
            ),
            startup_exception_patterns=_tuple_of_str(
                seniority_ceiling.get("startup_exception_patterns"),
            ),
        ),
        languages={str(key): str(value) for key, value in languages.items()},
        brand_floor=dict(brand_floor),
        disqualifying_hard_requirements=HardRequirementConfig(
            must_have_context_patterns=_tuple_of_str(
                hard_requirements.get("must_have_context_patterns"),
            ),
            nice_to_have_context_patterns=_tuple_of_str(
                hard_requirements.get("nice_to_have_context_patterns"),
            ),
            requirement_patterns=_tuple_of_str(hard_requirements.get("requirement_patterns")),
        ),
        usually_deprioritize=_tuple_of_str(data.get("usually_deprioritize")),
        honest_gaps=_tuple_of_str(data.get("honest_gaps")),
    )


@lru_cache(maxsize=1)
def load_relevance_filter(
    path: Path = CONFIG_DIR / "relevance_filter.yaml",
) -> RelevanceFilterConfig:
    data = _read_yaml_mapping(path)
    return RelevanceFilterConfig(
        version=str(data.get("version") or "relevance_filter_unknown"),
        target_location_required=bool(data.get("target_location_required", True)),
        excluded_title_department_patterns=_tuple_of_str(
            data.get("excluded_title_department_patterns"),
        ),
    )


def _read_yaml_mapping(path: Path) -> dict[str, object]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping in {path}")
    return data


def _tuple_of_str(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _dict_of_int(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): int(raw_value) for key, raw_value in value.items()}


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_threshold(thresholds: dict[object, object], key: str) -> int:
    value = thresholds.get(key)
    if not isinstance(value, int):
        raise ValueError(f"Invalid recommendation threshold: {key}")
    return value


def _expected_volume_min(audit_count: object) -> int | None:
    if not isinstance(audit_count, int):
        return None
    if audit_count <= 0:
        return 1
    return max(1, audit_count // 5)
