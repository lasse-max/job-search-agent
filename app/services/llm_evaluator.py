"""Claude-backed role judgment with validated structured output."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.config import DATA_DIR, CandidateProfileConfig
from app.models import CompanyConfig
from app.services.material import material_hash_for_row


PROMPT_VERSION = "role_evaluation_v2"
DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "role_evaluation_v1.md"
DEFAULT_LLM_CACHE_DIR = DATA_DIR / "evaluation_set" / "llm_cache"
DEFAULT_SPEND_LEDGER = DATA_DIR / "model_spend_ledger.json"
DEFAULT_ESTIMATED_EVAL_COST_USD = 0.004


class LLMAlignmentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_requirement: str = Field(min_length=1)
    candidate_evidence: str = Field(min_length=1)
    evidence_strength: Literal["strong", "medium", "weak"]


class LLMGapModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap: str = Field(min_length=1)
    severity: Literal["low", "medium", "high"]
    mitigation: str = Field(min_length=1)


class LLMHardBlockerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["disqualifying_hard_requirement"]
    evidence: str = Field(min_length=1, max_length=1200)


class LLMEvaluationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_family_fit: int = Field(ge=0, le=100)
    evidence_strength: int = Field(ge=0, le=100)
    scope_seniority: int = Field(ge=0, le=100)
    gap_manageability: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    advisory_recommendation: Literal["apply_now", "consider", "stretch", "skip", "blocked"]
    alignments: list[LLMAlignmentModel] = Field(min_length=1, max_length=6)
    gaps: list[LLMGapModel] = Field(min_length=1, max_length=6)
    hard_blockers: list[LLMHardBlockerModel] = Field(default_factory=list, max_length=4)
    uncertainties: list[str] = Field(default_factory=list, max_length=5)
    summary: str = Field(min_length=1, max_length=2400)

    @field_validator("alignments", "gaps", "hard_blockers", "uncertainties", mode="before")
    @classmethod
    def _coerce_json_encoded_list_fields(cls, value: object) -> object:
        if value == "":
            return []
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    @property
    def dimensions(self) -> dict[str, int]:
        return {
            "role_family_fit": self.role_family_fit,
            "evidence_strength": self.evidence_strength,
            "scope_seniority": self.scope_seniority,
            "gap_manageability": self.gap_manageability,
        }


@dataclass(frozen=True)
class LLMRoleRequest:
    row: sqlite3.Row
    company: CompanyConfig
    profile: CandidateProfileConfig


@dataclass(frozen=True)
class LLMEvaluationResult:
    output: LLMEvaluationOutput
    model_version: str
    prompt_version: str
    cost_usd: float = 0.0
    cache_hit: bool = False


class LLMProvider(Protocol):
    @property
    def model_version(self) -> str:
        """Model name or deterministic provider version."""

    def evaluate(self, request: LLMRoleRequest) -> LLMEvaluationResult:
        """Return validated role judgment."""


class LLMProviderError(RuntimeError):
    """Raised when a configured LLM provider cannot produce valid output."""


class ModelSpendCapExceeded(RuntimeError):
    """Raised before a model call would exceed the configured monthly cap."""


@dataclass
class ModelSpendTracker:
    ledger_path: Path = DEFAULT_SPEND_LEDGER
    monthly_cap_usd: float | None = None
    estimated_eval_cost_usd: float = DEFAULT_ESTIMATED_EVAL_COST_USD

    @classmethod
    def from_env(cls) -> ModelSpendTracker:
        return cls(
            ledger_path=Path(os.getenv("MODEL_SPEND_LEDGER_PATH", str(DEFAULT_SPEND_LEDGER))),
            monthly_cap_usd=_optional_float(os.getenv("MONTHLY_MODEL_SPEND_CAP_USD")),
            estimated_eval_cost_usd=float(
                os.getenv("MODEL_EVAL_ESTIMATED_COST_USD", str(DEFAULT_ESTIMATED_EVAL_COST_USD))
            ),
        )

    def assert_budget_allows(self) -> None:
        if self.monthly_cap_usd is None:
            return
        spent = self.current_month_spend()
        if spent + self.estimated_eval_cost_usd > self.monthly_cap_usd:
            raise ModelSpendCapExceeded(
                "monthly_model_spend_cap_exceeded: "
                f"spent ${spent:.4f}, cap ${self.monthly_cap_usd:.4f}, "
                f"estimated next eval ${self.estimated_eval_cost_usd:.4f}"
            )

    def record(self, cost_usd: float) -> None:
        if cost_usd <= 0:
            return
        ledger = self._read()
        month = _current_month()
        ledger[month] = round(float(ledger.get(month, 0.0)) + cost_usd, 6)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")

    def current_month_spend(self) -> float:
        return float(self._read().get(_current_month(), 0.0))

    def _read(self) -> dict[str, float]:
        if not self.ledger_path.exists():
            return {}
        data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {str(key): float(value) for key, value in data.items()}


@dataclass(frozen=True)
class ClaudeLLMProvider:
    api_key: str
    model: str = DEFAULT_CLAUDE_MODEL
    timeout_seconds: int = 30
    cache_dir: Path = DEFAULT_LLM_CACHE_DIR

    @property
    def model_version(self) -> str:
        return self.model

    def evaluate(self, request: LLMRoleRequest) -> LLMEvaluationResult:
        cache_path = _cache_path(self.cache_dir, self.model, request.row)
        if cache_path.exists():
            return _cached_result(cache_path)

        prompt = build_role_prompt(request)
        try:
            response = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 1800,
                    "system": _system_prompt(),
                    "messages": [{"role": "user", "content": prompt}],
                    "tools": [_evaluation_tool_schema()],
                    "tool_choice": {"type": "tool", "name": "submit_role_evaluation"},
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"claude_evaluation_failed: {type(exc).__name__}: {exc}") from exc

        payload = response.json()
        output = _parse_tool_output(payload)
        cost_usd = _estimated_cost(payload)
        result = LLMEvaluationResult(
            output=output,
            model_version=self.model,
            prompt_version=PROMPT_VERSION,
            cost_usd=cost_usd,
            cache_hit=False,
        )
        _write_cache(cache_path, result)
        return result


@dataclass(frozen=True)
class CachedLLMProvider:
    model: str = DEFAULT_CLAUDE_MODEL
    cache_dir: Path = DEFAULT_LLM_CACHE_DIR

    @classmethod
    def from_env(cls) -> CachedLLMProvider:
        return cls(
            model=os.getenv("ANTHROPIC_MODEL") or DEFAULT_CLAUDE_MODEL,
            cache_dir=Path(os.getenv("LLM_EVALUATION_CACHE_DIR", str(DEFAULT_LLM_CACHE_DIR))),
        )

    @property
    def model_version(self) -> str:
        return f"cached:{self.model}"

    def evaluate(self, request: LLMRoleRequest) -> LLMEvaluationResult:
        cache_path = _cache_path(self.cache_dir, self.model, request.row)
        if not cache_path.exists():
            raise LLMProviderError(
                "cached_llm_evaluation_missing: "
                f"{cache_path}. Populate data/evaluation_set/llm_cache with Claude "
                "before running the benchmark."
            )
        return _cached_result(cache_path)


def provider_from_env() -> LLMProvider | None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return ClaudeLLMProvider(
        api_key=api_key,
        model=os.getenv("ANTHROPIC_MODEL") or DEFAULT_CLAUDE_MODEL,
        cache_dir=Path(os.getenv("LLM_EVALUATION_CACHE_DIR", str(DEFAULT_LLM_CACHE_DIR))),
    )


def build_role_prompt(request: LLMRoleRequest) -> str:
    profile = request.profile
    row = request.row
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    role_payload = {
        "company": request.company.name,
        "company_tier": request.company.tier,
        "warm_path": request.company.warm_path,
        "title": row["title"],
        "department": row["department"] or "",
        "employment_type": row["employment_type"] if "employment_type" in row.keys() else "",
        "locations_json": row["locations_json"],
        "description_text": row["description_text"],
        "source_url": row["source_url"] if "source_url" in row.keys() else "",
    }
    profile_payload = {
        "positioning": profile.positioning,
        "primary_role_families": profile.primary_role_families,
        "approved_stretch_families": profile.approved_stretch_families,
        "usually_deprioritize": profile.usually_deprioritize,
        "honest_gaps": profile.honest_gaps,
        "languages": profile.languages,
        "seniority_ceiling": {
            "over_level_title_patterns": profile.seniority_ceiling.over_level_title_patterns,
            "startup_exception_patterns": profile.seniority_ceiling.startup_exception_patterns,
        },
        "disqualifying_hard_requirements": {
            "must_have_context_patterns": (
                profile.disqualifying_hard_requirements.must_have_context_patterns
            ),
            "nice_to_have_context_patterns": (
                profile.disqualifying_hard_requirements.nice_to_have_context_patterns
            ),
            "requirement_patterns": profile.disqualifying_hard_requirements.requirement_patterns,
        },
    }
    return (
        prompt_template
        + "\n\n## Candidate Profile JSON\n"
        + json.dumps(profile_payload, indent=2, sort_keys=True)
        + "\n\n## Role JSON\n"
        + json.dumps(role_payload, indent=2, sort_keys=True)
    )


def _system_prompt() -> str:
    return (
        "You are a strict job-role evaluator. Return only the requested tool call. "
        "Do not invent candidate evidence; use the supplied profile and job description."
    )


def _evaluation_tool_schema() -> dict[str, Any]:
    return {
        "name": "submit_role_evaluation",
        "description": "Submit validated role evaluation dimensions and evidence.",
        "input_schema": LLMEvaluationOutput.model_json_schema(),
    }


def _parse_tool_output(payload: dict[str, Any]) -> LLMEvaluationOutput:
    content = payload.get("content")
    if not isinstance(content, list):
        raise LLMProviderError("claude_response_missing_content")
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use" and block.get("name") == "submit_role_evaluation":
            raw_input = block.get("input")
            if not isinstance(raw_input, dict):
                raise LLMProviderError("claude_tool_input_not_object")
            try:
                return LLMEvaluationOutput.model_validate(raw_input)
            except ValidationError as exc:
                raise LLMProviderError(
                    f"claude_tool_input_validation_failed: {exc}"
                ) from exc
    raise LLMProviderError("claude_response_missing_submit_role_evaluation_tool")


def _estimated_cost(payload: dict[str, Any]) -> float:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return 0.0
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    input_rate = float(os.getenv("ANTHROPIC_INPUT_COST_PER_1K_USD", "0.0008"))
    output_rate = float(os.getenv("ANTHROPIC_OUTPUT_COST_PER_1K_USD", "0.004"))
    return round((input_tokens / 1000 * input_rate) + (output_tokens / 1000 * output_rate), 6)


def _cache_path(cache_dir: Path, model: str, row: sqlite3.Row) -> Path:
    key = hashlib.sha256(
        json.dumps(
            {
                "prompt_version": PROMPT_VERSION,
                "model": model,
                "input_hash": material_hash_for_row(row),
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return cache_dir / f"{key}.json"


def _cached_result(path: Path) -> LLMEvaluationResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return LLMEvaluationResult(
        output=LLMEvaluationOutput.model_validate(payload["output"]),
        model_version=str(payload["model_version"]),
        prompt_version=str(payload["prompt_version"]),
        cost_usd=0.0,
        cache_hit=True,
    )


def _write_cache(path: Path, result: LLMEvaluationResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model_version": result.model_version,
        "prompt_version": result.prompt_version,
        "output": result.output.model_dump(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_cached_evaluation(
    *,
    cache_dir: Path,
    model: str,
    row: sqlite3.Row,
    output: LLMEvaluationOutput,
    prompt_version: str = PROMPT_VERSION,
) -> Path:
    path = _cache_path(cache_dir, model, row)
    _write_cache(
        path,
        LLMEvaluationResult(
            output=output,
            model_version=model,
            prompt_version=prompt_version,
            cache_hit=False,
        ),
    )
    return path


def _optional_float(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return float(value)


def _current_month() -> str:
    from app.models import utc_now

    return utc_now()[:7]
