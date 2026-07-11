"""Canonical models for the first discovery vertical slice.

The models are plain dataclasses so the Checkpoint B slice can run in a clean
Python environment without requiring dependency installation first. Stage 1 can
later move validation to Pydantic without changing the data boundary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


AvailabilityState = Literal["open", "unavailable"]
EvaluationRecommendation = Literal["apply_now", "consider", "stretch", "skip", "blocked"]
FeasibilityState = Literal["viable", "sponsorship_required", "uncertain", "blocked"]
ReviewState = Literal[
    "new",
    "interested",
    "approved",
    "dismissed",
    "snoozed",
    "duplicate",
    "closed",
]
EstimatedLevel = Literal["L3", "L4", "L5", "L6", "L7+", "unknown"]


def utc_now() -> str:
    """Return an ISO timestamp with a UTC offset."""

    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class CompanyConfig:
    name: str
    tier: int
    enabled: bool
    ats_type: str
    source_key: str
    careers_url: str
    target_locations: list[str]
    target_role_family_notes: str
    warm_path: bool
    expected_volume_min: int | None = None


@dataclass(frozen=True)
class FetchResult:
    source_type: str
    source_key: str
    url: str
    status: str
    http_status: int | None
    duration_ms: int
    response_body: str
    error: str | None = None


@dataclass(frozen=True)
class SourceHealth:
    status: Literal["healthy", "degraded", "failing", "unsupported", "disabled"]
    fetched_count: int
    error_summary: str | None = None


@dataclass(frozen=True)
class JobPosting:
    company: str
    title: str
    locations: list[str]
    department: str | None
    employment_type: str | None
    description_text: str
    source_type: str
    source_url: str
    source_job_id: str
    source_posted_at: str | None
    raw_payload_hash: str
    canonical_key: str
    availability_state: AvailabilityState = "open"


@dataclass(frozen=True)
class Alignment:
    job_requirement: str
    candidate_evidence: str
    evidence_strength: Literal["strong", "medium", "weak"]


@dataclass(frozen=True)
class Gap:
    gap: str
    severity: Literal["low", "medium", "high"]
    mitigation: str


@dataclass(frozen=True)
class HardBlocker:
    type: str
    evidence: str


@dataclass(frozen=True)
class RoleEvaluation:
    role_fit_score: int
    confidence: float
    dimensions: dict[str, int]
    feasibility: dict[str, str]
    strategic_priority: dict[str, str | bool]
    recommendation: EvaluationRecommendation
    hard_blockers: list[HardBlocker] = field(default_factory=list)
    alignments: list[Alignment] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)
    estimated_level: EstimatedLevel = "unknown"
    level_confidence: int = 0
    level_rationale: str = "Insufficient evidence to estimate level."
    summary: str = ""

    def to_jsonable(self) -> dict[str, Any]:
        return asdict(self)
