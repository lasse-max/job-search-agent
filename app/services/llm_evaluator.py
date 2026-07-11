"""Claude-backed role judgment with validated structured output."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.config import DATA_DIR, CandidateProfileConfig
from app.models import CompanyConfig
from app.services.material import material_hash_for_row


PROMPT_VERSION = "role_evaluation_v5"
DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "role_evaluation_v1.md"
DEFAULT_LLM_CACHE_DIR = DATA_DIR / "evaluation_set" / "llm_cache"
DEFAULT_SPEND_LEDGER = DATA_DIR / "model_spend_ledger.json"
DEFAULT_ESTIMATED_EVAL_COST_USD = 0.004
RETRYABLE_CLAUDE_STATUS_CODES = {429, 529}
CLAUDE_MAX_ATTEMPTS = 3


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
    estimated_level: Literal["L3", "L4", "L5", "L6", "L7+", "unknown"]
    level_confidence: int = Field(ge=0, le=100)
    level_rationale: str = Field(
        min_length=1,
        max_length=600,
    )
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

    @field_validator("level_rationale")
    @classmethod
    def _require_role_only_level_rationale(cls, value: str) -> str:
        lowered = value.casefold()
        forbidden = re.search(
            (
                r"\bcandidate(?:'s)?\b|\bapplicant(?:'s)?\b|\bprofile narrative\b"
                r"|\bpromotions?\b"
                r"|\b(?:eight|8)\s+years?\b.{0,80}\bgoogle\b"
                r"|\byears?\s+in\s+(?:a\s+)?comparable role\b"
                r"|\bcompany tier\b"
                r"|\b(?:company|employer|brand)\b.{0,20}\btier[-\s]?[123]\b"
                r"|\btier[-\s]?[123]\b.{0,20}\b(?:company|employer|brand)\b"
            ),
            lowered,
        )
        if forbidden:
            raise ValueError(
                "level_rationale must estimate the posted role from JD evidence only; "
                f"forbidden phrase: {forbidden.group(0)!r}"
            )
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

    def __init__(
        self,
        message: str,
        *,
        retryable_output: bool = False,
        cost_usd: float = 0.0,
    ) -> None:
        super().__init__(message)
        self.retryable_output = retryable_output
        self.cost_usd = cost_usd


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
    _retry_feedback: dict[str, str] = field(
        default_factory=dict,
        init=False,
        repr=False,
        compare=False,
    )

    @property
    def model_version(self) -> str:
        return self.model

    def evaluate(self, request: LLMRoleRequest) -> LLMEvaluationResult:
        cache_path = _cache_path(self.cache_dir, self.model, request.row)
        if cache_path.exists():
            try:
                result = _cached_result(cache_path)
                _validate_role_level_consistency(result.output, request.row)
                return result
            except LLMProviderError:
                cache_path.unlink(missing_ok=True)

        cache_key = str(cache_path)
        prompt = build_role_prompt(request)
        retry_feedback = self._retry_feedback.pop(cache_key, None)
        if retry_feedback:
            prompt = (
                f"{prompt}\n\n"
                "CORRECTION FOR THIS ONE RETRY: The prior tool call failed validation. "
                "Return exactly the declared submit_role_evaluation fields, with no "
                "extra keys, and correct the validation issue below.\n"
                f"{retry_feedback[:1600]}"
            )
        try:
            response = _post_claude_message(
                api_key=self.api_key,
                model=self.model,
                prompt=prompt,
                timeout_seconds=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"claude_evaluation_failed: {type(exc).__name__}: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            self._retry_feedback[cache_key] = "The response was not valid JSON."
            raise LLMProviderError(
                "claude_response_invalid_json",
                retryable_output=True,
                cost_usd=DEFAULT_ESTIMATED_EVAL_COST_USD,
            ) from exc
        try:
            output = _normalize_role_level_output(
                _parse_tool_output(payload),
                request.row,
            )
            _validate_role_level_consistency(output, request.row)
        except LLMProviderError as exc:
            if exc.retryable_output:
                self._retry_feedback[cache_key] = str(exc)
            raise LLMProviderError(
                str(exc),
                retryable_output=exc.retryable_output,
                cost_usd=_estimated_cost(payload) or DEFAULT_ESTIMATED_EVAL_COST_USD,
            ) from exc
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
        result = _cached_result(cache_path)
        _validate_role_level_consistency(result.output, request.row)
        return result


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
        "company_size_stage": "unknown_unless_stated_in_jd",
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
        "Do not invent candidate evidence; use the supplied profile and job description. "
        "Estimate estimated_level for the posted role itself from the Role JSON only, "
        "never from the candidate's career history."
    )


def _post_claude_message(
    *,
    api_key: str,
    model: str,
    prompt: str,
    timeout_seconds: int,
) -> httpx.Response:
    last_error: httpx.HTTPError | None = None
    for attempt in range(CLAUDE_MAX_ATTEMPTS):
        try:
            response = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 1800,
                    "system": _system_prompt(),
                    "messages": [{"role": "user", "content": prompt}],
                    "tools": [_evaluation_tool_schema()],
                    "tool_choice": {"type": "tool", "name": "submit_role_evaluation"},
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt >= CLAUDE_MAX_ATTEMPTS - 1 or not _is_retryable_claude_error(exc):
                raise
            time.sleep(0.25 * (2**attempt))
    assert last_error is not None
    raise last_error


def _is_retryable_claude_error(exc: httpx.HTTPError) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_CLAUDE_STATUS_CODES
    return False


def _evaluation_tool_schema() -> dict[str, Any]:
    schema = LLMEvaluationOutput.model_json_schema()
    required = set(schema.get("required") or [])
    required.update({"estimated_level", "level_confidence", "level_rationale"})
    schema["required"] = sorted(required)
    return {
        "name": "submit_role_evaluation",
        "description": "Submit validated role evaluation dimensions and evidence.",
        "input_schema": schema,
    }


def _parse_tool_output(payload: dict[str, Any]) -> LLMEvaluationOutput:
    content = payload.get("content")
    if not isinstance(content, list):
        raise LLMProviderError(
            "claude_response_missing_content",
            retryable_output=True,
        )
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use" and block.get("name") == "submit_role_evaluation":
            raw_input = block.get("input")
            if not isinstance(raw_input, dict):
                raise LLMProviderError(
                    "claude_tool_input_not_object",
                    retryable_output=True,
                )
            normalized_input = dict(raw_input)
            rationale_aliases = [
                normalized_input.pop(alias, None)
                for alias in (
                    "level_rationale_short",
                    "level_rationale_context",
                    "level_rationale_expanded",
                )
            ]
            rationale = normalized_input.get("level_rationale")
            if not isinstance(rationale, str) or len(rationale) > 600:
                rationale = next(
                    (
                        alias
                        for alias in rationale_aliases
                        if isinstance(alias, str) and len(alias) <= 600
                    ),
                    rationale,
                )
            if isinstance(rationale, str):
                normalized_input["level_rationale"] = _sanitize_level_rationale(rationale)
            rationale_confidence = normalized_input.pop(
                "level_rationale_confidence",
                None,
            )
            if "level_confidence" not in normalized_input and rationale_confidence is not None:
                normalized_input["level_confidence"] = rationale_confidence
            try:
                return LLMEvaluationOutput.model_validate(normalized_input)
            except ValidationError as exc:
                raise LLMProviderError(
                    f"claude_tool_input_validation_failed: {exc}",
                    retryable_output=True,
                ) from exc
    raise LLMProviderError(
        "claude_response_missing_submit_role_evaluation_tool",
        retryable_output=True,
    )


def _sanitize_level_rationale(value: str) -> str:
    """Keep role evidence while removing an appended candidate-comparison clause."""

    value = re.sub(r"\s+", " ", value).strip()
    clauses = re.split(r"(?<=[.!?])\s+|\s*;\s*", value)
    kept: list[str] = []
    candidate_pattern = re.compile(
        r"\b(?:candidate|applicant)(?:'s)?\b",
        flags=re.IGNORECASE,
    )
    for clause in clauses:
        match = candidate_pattern.search(clause)
        if not match:
            kept.append(clause)
            continue
        role_prefix = clause[: match.start()].rstrip(" ,:-")
        if len(role_prefix) >= 25 and re.search(
            r"\b(?:jd|role|title|scope|required|requires|years?|management|reports? to)\b",
            role_prefix,
            flags=re.IGNORECASE,
        ):
            kept.append(role_prefix)
    if kept:
        value = ". ".join(part.rstrip(".") for part in kept if part).strip()
        if value and not value.endswith("."):
            value += "."
    if len(value) <= 600:
        return value
    shortened = value[:597]
    boundary = max(shortened.rfind(". "), shortened.rfind("; "))
    if boundary >= 300:
        shortened = shortened[: boundary + 1]
    else:
        shortened = shortened.rsplit(" ", 1)[0].rstrip(" ,;:") + "."
    return shortened


def _normalize_role_level_output(
    output: LLMEvaluationOutput,
    row: sqlite3.Row,
) -> LLMEvaluationOutput:
    """Apply hard JD anchors without turning seniority into a filter."""

    title = str(row["title"] or "")
    description = str(row["description_text"] or "")
    text = f"{title} {description}"
    years = _minimum_required_years(text)
    manager_of_managers = bool(
        re.search(
            (
                r"\bmanag(?:e|es|ing)\s+(?:a\s+)?(?:team\s+of\s+)?managers\b"
                r"|\bmanager[- ]of[- ]managers\b"
                r"|\bdirect reports?\b.{0,50}\bmanagers\b"
            ),
            text,
            flags=re.IGNORECASE,
        )
    )
    rank = {"L3": 3, "L4": 4, "L5": 5, "L6": 6, "L7+": 7, "unknown": 0}[
        output.estimated_level
    ]
    if re.search(r"\bintern(?:ship)?\b", title, flags=re.IGNORECASE) and rank not in {0, 3}:
        return output.model_copy(
            update={
                "estimated_level": "L3",
                "level_confidence": max(output.level_confidence, 85),
                "level_rationale": (
                    "The posted role is an internship, which maps to the L3 anchor; "
                    "no higher-scope JD evidence overrides that signal."
                ),
            }
        )
    if years >= 12 and rank < 6:
        return output.model_copy(
            update={
                "estimated_level": "L6",
                "level_confidence": max(output.level_confidence, 85),
                "level_rationale": (
                    f"The JD requires at least {years} years of professional experience, "
                    "a hard seniority anchor that maps the posted role to L6."
                ),
            }
        )
    if manager_of_managers and rank < 6:
        return output.model_copy(
            update={
                "estimated_level": "L6",
                "level_confidence": max(output.level_confidence, 85),
                "level_rationale": (
                    "The JD assigns manager-of-managers scope, a hard seniority anchor "
                    "that maps the posted role to L6."
                ),
            }
        )
    return output


def _validate_role_level_consistency(
    output: LLMEvaluationOutput,
    row: sqlite3.Row,
) -> None:
    """Reject obvious role-level contradictions before they enter the cache."""

    title = str(row["title"] or "")
    description = str(row["description_text"] or "")
    text = f"{title} {description}"
    rank = {"L3": 3, "L4": 4, "L5": 5, "L6": 6, "L7+": 7, "unknown": 0}[
        output.estimated_level
    ]
    if re.search(r"\bintern(?:ship)?\b", title, flags=re.IGNORECASE) and rank not in {0, 3}:
        raise LLMProviderError(
            "claude_role_level_inconsistent: internship role must be L3 or unknown",
            retryable_output=True,
        )
    if _minimum_required_years(text) >= 12 and rank < 6:
        raise LLMProviderError(
            "claude_role_level_inconsistent: role requiring 12+ years must be L6+",
            retryable_output=True,
        )
    if re.search(
        (
            r"\bmanag(?:e|es|ing)\s+(?:a\s+)?(?:team\s+of\s+)?managers\b"
            r"|\bmanager[- ]of[- ]managers\b"
            r"|\bdirect reports?\b.{0,50}\bmanagers\b"
        ),
        text,
        flags=re.IGNORECASE,
    ) and rank < 6:
        raise LLMProviderError(
            "claude_role_level_inconsistent: manager-of-managers role must be L6+",
            retryable_output=True,
        )


def _minimum_required_years(text: str) -> int:
    values = [
        int(match.group("years"))
        for match in re.finditer(
            (
                r"\b(?P<years>\d{1,2})\s*"
                r"(?:\+|to\s+\d{1,2}\+?|[-–]\s*\d{1,2}\+?)?\s+years?\b"
                r"(?:\s+of)?[^.;\n]{0,60}\bexperience\b"
            ),
            text,
            flags=re.IGNORECASE,
        )
    ]
    return max(values, default=0)


def _estimated_cost(payload: dict[str, Any]) -> float:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return 0.0
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    input_rate = float(os.getenv("ANTHROPIC_INPUT_COST_PER_1K_USD", "0.0008"))
    output_rate = float(os.getenv("ANTHROPIC_OUTPUT_COST_PER_1K_USD", "0.004"))
    return round((input_tokens / 1000 * input_rate) + (output_tokens / 1000 * output_rate), 6)


def _cache_path(
    cache_dir: Path,
    model: str,
    row: sqlite3.Row,
    *,
    prompt_version: str = PROMPT_VERSION,
) -> Path:
    key = hashlib.sha256(
        json.dumps(
            {
                "prompt_version": prompt_version,
                "model": model,
                "input_hash": material_hash_for_row(row),
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return cache_dir / f"{key}.json"


def _cached_result(path: Path) -> LLMEvaluationResult:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return LLMEvaluationResult(
            output=LLMEvaluationOutput.model_validate(payload["output"]),
            model_version=str(payload["model_version"]),
            prompt_version=str(payload["prompt_version"]),
            cost_usd=0.0,
            cache_hit=True,
        )
    except (OSError, KeyError, ValueError) as exc:
        raise LLMProviderError(
            f"cached_llm_evaluation_invalid: {path}: {type(exc).__name__}: {exc}"
        ) from exc


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
    path = _cache_path(cache_dir, model, row, prompt_version=prompt_version)
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
