"""Offline benchmark harness for the labelled evaluation set."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from app.adapters.utils import clean_html, compact_text
from app.config import DATA_DIR
from app.models import CompanyConfig
from app.services.evaluate import evaluate_role, relevance_decision
from app.services.llm_evaluator import CachedLLMProvider, LLMProvider


DEFAULT_EVALUATION_SET = DATA_DIR / "evaluation_set" / "evaluation_set.yaml"
DEFAULT_JD_CACHE_DIR = DATA_DIR / "evaluation_set" / "jd_cache"
DEFAULT_LIVE_NOISE_SET = DATA_DIR / "evaluation_set" / "live_noise_labels.yaml"
DEFAULT_LIVE_NOISE_PRECISION_SET = DATA_DIR / "evaluation_set" / "live_noise_precision_set.yaml"
DEFAULT_REPORT_DIR = DATA_DIR / "evaluation_set" / "reports"
APPLY_CONSIDER = {"apply_now", "consider"}
LABELLED_RECOMMENDATIONS = {"apply_now", "consider", "stretch", "skip", "blocked"}
MAX_CACHED_CHARS = 12000


@dataclass(frozen=True)
class BenchmarkResult:
    role_id: str
    company: str
    role_title: str
    label: str
    expected_recommendation: str
    actual_recommendation: str
    expected_feasibility: str
    actual_feasibility: str
    expected_tier: str
    actual_tier: str
    expected_blocked: bool
    actual_blocked: bool
    fit_score: int
    recommendation_match: bool
    surface_match: bool
    blocker_match: bool
    feasibility_match: bool
    fit_band_match: bool
    evaluator_version: str


@dataclass(frozen=True)
class BenchmarkMetrics:
    total_roles: int
    exact_recommendation_matches: int
    exact_recommendation_match_rate: float
    apply_consider_expected: int
    apply_consider_recalled: int
    apply_consider_recall: float
    surfaced_count: int
    surfaced_correct: int
    digest_precision: float
    blocker_accuracy: float
    fit_band_agreement: float
    feasibility_correctness: float

    @property
    def recall_passes(self) -> bool:
        return self.apply_consider_recall >= 0.95


@dataclass(frozen=True)
class BenchmarkRun:
    metrics: BenchmarkMetrics
    results: list[BenchmarkResult]
    markdown_path: Path
    csv_path: Path
    label_set_path: Path
    evaluator_versions: tuple[str, ...]


@dataclass(frozen=True)
class LiveNoiseBenchmarkResult:
    role_id: str
    company: str
    role_title: str
    expected_recommendation: str
    actual_recommendation: str
    fit_score: int
    surface_match: bool
    evaluator_version: str


@dataclass(frozen=True)
class LiveNoiseBenchmarkMetrics:
    labelled_roles: int
    surfaced_count: int
    surfaced_correct: int
    digest_precision: float

    @property
    def precision_passes(self) -> bool:
        return self.labelled_roles > 0 and self.digest_precision >= 0.80


@dataclass(frozen=True)
class LiveNoiseBenchmarkRun:
    metrics: LiveNoiseBenchmarkMetrics
    results: list[LiveNoiseBenchmarkResult]
    markdown_path: Path
    csv_path: Path
    label_set_path: Path
    label_set_purpose: str
    evaluator_versions: tuple[str, ...]


@dataclass(frozen=True)
class GateRecallBenchmarkResult:
    role_id: str
    company: str
    role_title: str
    expected_recommendation: str
    expected_should_pass_gate: bool
    actual_passed_gate: bool
    gate_reason: str


@dataclass(frozen=True)
class GateRecallBenchmarkMetrics:
    labelled_roles: int
    expected_pass_count: int
    expected_pass_recalled: int
    gate_recall: float
    false_skips: int

    @property
    def recall_passes(self) -> bool:
        return self.expected_pass_count == 0 or self.gate_recall >= 0.95


@dataclass(frozen=True)
class GateRecallBenchmarkRun:
    metrics: GateRecallBenchmarkMetrics
    results: list[GateRecallBenchmarkResult]
    markdown_path: Path
    csv_path: Path
    label_set_path: Path


def run_benchmark(
    *,
    evaluation_set_path: Path = DEFAULT_EVALUATION_SET,
    cache_dir: Path = DEFAULT_JD_CACHE_DIR,
    report_dir: Path = DEFAULT_REPORT_DIR,
    llm_provider: LLMProvider | None = None,
) -> BenchmarkRun:
    examples = load_evaluation_set(evaluation_set_path)
    provider = llm_provider or CachedLLMProvider.from_env()
    results = [
        _evaluate_example(example, cache_dir / f"{example['id']}.txt", provider)
        for example in examples
    ]
    metrics = _metrics(results)
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "calibration_report.csv"
    markdown_path = report_dir / "calibration_report.md"
    _write_csv(csv_path, results)
    evaluator_versions = _benchmark_evaluator_versions(results)
    _write_markdown(
        markdown_path,
        metrics,
        results,
        label_set_path=evaluation_set_path,
        evaluator_versions=evaluator_versions,
    )
    return BenchmarkRun(
        metrics=metrics,
        results=results,
        markdown_path=markdown_path,
        csv_path=csv_path,
        label_set_path=evaluation_set_path,
        evaluator_versions=evaluator_versions,
    )


def run_live_noise_benchmark(
    *,
    live_noise_set_path: Path = DEFAULT_LIVE_NOISE_PRECISION_SET,
    report_dir: Path = DEFAULT_REPORT_DIR,
    label_set_purpose: str = "gate_passer_precision",
    llm_provider: LLMProvider | None = None,
) -> LiveNoiseBenchmarkRun:
    examples = load_live_noise_set(live_noise_set_path) if live_noise_set_path.exists() else []
    labelled = _labelled_examples(examples)
    provider = llm_provider or CachedLLMProvider.from_env()
    results = [_evaluate_live_noise_example(example, provider) for example in labelled]
    metrics = _live_noise_metrics(results)
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "live_noise_precision_report.csv"
    markdown_path = report_dir / "live_noise_precision_report.md"
    _write_live_noise_csv(csv_path, results)
    evaluator_versions = _evaluator_versions(results)
    _write_live_noise_markdown(
        markdown_path,
        metrics,
        results,
        label_set_path=live_noise_set_path,
        label_set_purpose=label_set_purpose,
        evaluator_versions=evaluator_versions,
    )
    return LiveNoiseBenchmarkRun(
        metrics=metrics,
        results=results,
        markdown_path=markdown_path,
        csv_path=csv_path,
        label_set_path=live_noise_set_path,
        label_set_purpose=label_set_purpose,
        evaluator_versions=evaluator_versions,
    )


def run_gate_recall_benchmark(
    *,
    live_noise_set_path: Path = DEFAULT_LIVE_NOISE_SET,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> GateRecallBenchmarkRun:
    examples = load_live_noise_set(live_noise_set_path) if live_noise_set_path.exists() else []
    labelled = _labelled_examples(examples)
    results = [_evaluate_gate_recall_example(example) for example in labelled]
    metrics = _gate_recall_metrics(results)
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "live_noise_gate_recall_report.csv"
    markdown_path = report_dir / "live_noise_gate_recall_report.md"
    _write_gate_recall_csv(csv_path, results)
    _write_gate_recall_markdown(markdown_path, metrics, results, live_noise_set_path)
    return GateRecallBenchmarkRun(
        metrics=metrics,
        results=results,
        markdown_path=markdown_path,
        csv_path=csv_path,
        label_set_path=live_noise_set_path,
    )


def load_evaluation_set(path: Path = DEFAULT_EVALUATION_SET) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return _load_loose_evaluation_set(text)
    if not isinstance(data, dict) or not isinstance(data.get("evaluation_set"), list):
        raise ValueError(f"Expected evaluation_set list in {path}")
    return [dict(item) for item in data["evaluation_set"]]


def load_live_noise_set(path: Path = DEFAULT_LIVE_NOISE_SET) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("live_noise_set"), list):
        raise ValueError(f"Expected live_noise_set list in {path}")
    return [dict(item) for item in data["live_noise_set"]]


def labelled_live_noise_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len(_labelled_examples(load_live_noise_set(path)))


def _labelled_examples(examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        example
        for example in examples
        if str(example.get("expected_recommendation") or "") in LABELLED_RECOMMENDATIONS
    ]


def _load_loose_evaluation_set(text: str) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_hard_blockers = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith("  - id: "):
            if current is not None:
                examples.append(current)
            current = {"id": _clean_scalar(line.split(": ", 1)[1])}
            in_hard_blockers = False
            continue
        if current is None or not line.startswith("    "):
            continue
        if stripped.startswith("- type:") and in_hard_blockers:
            current.setdefault("hard_blockers", []).append(
                {"type": _clean_scalar(stripped.split(": ", 1)[1])}
            )
            continue
        if ": " not in stripped:
            continue
        key, value = stripped.split(": ", 1)
        if key == "hard_blockers":
            current[key] = [] if value.strip() == "[]" else []
            in_hard_blockers = True
            continue
        current[key] = _clean_scalar(value)
        in_hard_blockers = False
    if current is not None:
        examples.append(current)
    return examples


def _clean_scalar(value: str) -> str:
    value = value.split(" #", 1)[0].strip()
    if value in {"[]", "null"}:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value


def refresh_jd_cache(
    *,
    evaluation_set_path: Path = DEFAULT_EVALUATION_SET,
    cache_dir: Path = DEFAULT_JD_CACHE_DIR,
    force: bool = False,
) -> list[Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for example in load_evaluation_set(evaluation_set_path):
        path = cache_dir / f"{example['id']}.txt"
        if path.exists() and not force:
            continue
        text, status = _fetch_source_text(str(example["jd_source"]))
        if not text:
            text = _fallback_snapshot(example, status)
        path.write_text(_cache_document(example, text, status), encoding="utf-8")
        written.append(path)
    return written


def _evaluate_example(
    example: dict[str, Any],
    cache_path: Path,
    llm_provider: LLMProvider,
) -> BenchmarkResult:
    if not cache_path.exists():
        raise FileNotFoundError(
            f"Missing cached JD snapshot for {example['id']}: {cache_path}"
        )
    description_text = cache_path.read_text(encoding="utf-8")
    row = {
        "title": str(example["role_title"]),
        "locations_json": json.dumps([str(example["location"])]),
        "department": _department_hint(str(example["role_title"]), description_text),
        "employment_type": "",
        "description_text": description_text,
    }
    company = _company_config(example)
    evaluation = evaluate_role(row, company, llm_provider=llm_provider)
    evaluator_version = str(
        evaluation.provenance.get("model_version")
        or evaluation.provenance.get("evaluator_version")
        or "unknown"
    )
    actual_tier = str(evaluation.strategic_priority["company_tier"])
    expected_tier = str(example["expected_strategic_tier"])
    expected_recommendation = str(example["expected_recommendation"])
    actual_recommendation = evaluation.recommendation
    expected_feasibility = str(example["expected_feasibility"])
    actual_feasibility = evaluation.feasibility["state"]
    expected_blocked = bool(example.get("hard_blockers")) or expected_recommendation == "blocked"
    actual_blocked = bool(evaluation.hard_blockers) or actual_recommendation == "blocked"
    return BenchmarkResult(
        role_id=str(example["id"]),
        company=str(example["company"]),
        role_title=str(example["role_title"]),
        label=str(example["label"]),
        expected_recommendation=expected_recommendation,
        actual_recommendation=actual_recommendation,
        expected_feasibility=expected_feasibility,
        actual_feasibility=actual_feasibility,
        expected_tier=expected_tier,
        actual_tier=actual_tier,
        expected_blocked=expected_blocked,
        actual_blocked=actual_blocked,
        fit_score=evaluation.role_fit_score,
        recommendation_match=actual_recommendation == expected_recommendation,
        surface_match=(
            actual_recommendation in APPLY_CONSIDER
            if expected_recommendation in APPLY_CONSIDER
            else actual_recommendation not in APPLY_CONSIDER
        ),
        blocker_match=actual_blocked == expected_blocked,
        feasibility_match=_feasibility_matches(expected_feasibility, actual_feasibility),
        fit_band_match=_fit_band(actual_recommendation) == _fit_band(expected_recommendation),
        evaluator_version=evaluator_version,
    )


def _evaluate_live_noise_example(
    example: dict[str, Any],
    llm_provider: LLMProvider,
) -> LiveNoiseBenchmarkResult:
    description_text = str(
        example.get("description_text") or example.get("description_excerpt") or ""
    )
    row = {
        "title": str(example["role_title"]),
        "locations_json": json.dumps([str(example["location"])]),
        "department": str(example.get("department") or ""),
        "employment_type": str(example.get("employment_type") or ""),
        "description_text": description_text,
        "source_url": str(example.get("source_url") or ""),
    }
    company = CompanyConfig(
        name=str(example["company"]),
        tier=int(example.get("company_tier") or 3),
        enabled=True,
        ats_type="manual",
        source_key=str(example.get("stable_id") or example["id"]).lower(),
        careers_url=str(example.get("source_url") or ""),
        target_locations=[str(example["location"])],
        target_role_family_notes="Live-noise precision label.",
        warm_path=bool(example.get("warm_path", False)),
    )
    evaluation = evaluate_role(row, company, llm_provider=llm_provider)
    expected = str(example["expected_recommendation"])
    evaluator_version = str(
        evaluation.provenance.get("model_version")
        or evaluation.provenance.get("evaluator_version")
        or "unknown"
    )
    return LiveNoiseBenchmarkResult(
        role_id=str(example["id"]),
        company=str(example["company"]),
        role_title=str(example["role_title"]),
        expected_recommendation=expected,
        actual_recommendation=evaluation.recommendation,
        fit_score=evaluation.role_fit_score,
        surface_match=(
            evaluation.recommendation in APPLY_CONSIDER
            if expected in APPLY_CONSIDER
            else evaluation.recommendation not in APPLY_CONSIDER
        ),
        evaluator_version=evaluator_version,
    )


def _evaluate_gate_recall_example(example: dict[str, Any]) -> GateRecallBenchmarkResult:
    row = {
        "title": str(example["role_title"]),
        "locations_json": json.dumps([str(example["location"])]),
        "department": str(example.get("department") or ""),
        "employment_type": str(example.get("employment_type") or ""),
        "description_text": str(
            example.get("description_text") or example.get("description_excerpt") or ""
        ),
        "source_url": str(example.get("source_url") or ""),
    }
    company = CompanyConfig(
        name=str(example["company"]),
        tier=int(example.get("company_tier") or 3),
        enabled=True,
        ats_type="manual",
        source_key=str(example.get("stable_id") or example["id"]).lower(),
        careers_url=str(example.get("source_url") or ""),
        target_locations=[str(example["location"])],
        target_role_family_notes="Live-noise gate-recall label.",
        warm_path=bool(example.get("warm_path", False)),
    )
    decision = relevance_decision(row, company)
    expected = str(example["expected_recommendation"])
    expected_should_pass = expected != "skip"
    return GateRecallBenchmarkResult(
        role_id=str(example["id"]),
        company=str(example["company"]),
        role_title=str(example["role_title"]),
        expected_recommendation=expected,
        expected_should_pass_gate=expected_should_pass,
        actual_passed_gate=decision.should_evaluate,
        gate_reason=decision.reason,
    )


def _metrics(results: list[BenchmarkResult]) -> BenchmarkMetrics:
    expected_surface = [
        result for result in results if result.expected_recommendation in APPLY_CONSIDER
    ]
    recalled = [
        result for result in expected_surface if result.actual_recommendation in APPLY_CONSIDER
    ]
    surfaced = [result for result in results if result.actual_recommendation in APPLY_CONSIDER]
    surface_correct = [
        result for result in surfaced if result.expected_recommendation in APPLY_CONSIDER
    ]
    return BenchmarkMetrics(
        total_roles=len(results),
        exact_recommendation_matches=sum(
            1 for result in results if result.recommendation_match
        ),
        exact_recommendation_match_rate=_ratio(
            sum(1 for result in results if result.recommendation_match),
            len(results),
        ),
        apply_consider_expected=len(expected_surface),
        apply_consider_recalled=len(recalled),
        apply_consider_recall=_ratio(len(recalled), len(expected_surface)),
        surfaced_count=len(surfaced),
        surfaced_correct=len(surface_correct),
        digest_precision=_ratio(len(surface_correct), len(surfaced)),
        blocker_accuracy=_ratio(
            sum(1 for result in results if result.blocker_match),
            len(results),
        ),
        fit_band_agreement=_ratio(
            sum(1 for result in results if result.fit_band_match),
            len(results),
        ),
        feasibility_correctness=_ratio(
            sum(1 for result in results if result.feasibility_match),
            len(results),
        ),
    )


def _live_noise_metrics(results: list[LiveNoiseBenchmarkResult]) -> LiveNoiseBenchmarkMetrics:
    surfaced = [result for result in results if result.actual_recommendation in APPLY_CONSIDER]
    surfaced_correct = [
        result for result in surfaced if result.expected_recommendation in APPLY_CONSIDER
    ]
    return LiveNoiseBenchmarkMetrics(
        labelled_roles=len(results),
        surfaced_count=len(surfaced),
        surfaced_correct=len(surfaced_correct),
        digest_precision=_ratio(len(surfaced_correct), len(surfaced)),
    )


def _gate_recall_metrics(results: list[GateRecallBenchmarkResult]) -> GateRecallBenchmarkMetrics:
    expected_pass = [result for result in results if result.expected_should_pass_gate]
    recalled = [result for result in expected_pass if result.actual_passed_gate]
    false_skips = len(expected_pass) - len(recalled)
    return GateRecallBenchmarkMetrics(
        labelled_roles=len(results),
        expected_pass_count=len(expected_pass),
        expected_pass_recalled=len(recalled),
        gate_recall=_ratio(len(recalled), len(expected_pass)),
        false_skips=false_skips,
    )


def _write_csv(path: Path, results: list[BenchmarkResult]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(results[0].__dict__.keys()),
            lineterminator="\n",
        )
        writer.writeheader()
        for result in results:
            writer.writerow(result.__dict__)


def _write_live_noise_csv(path: Path, results: list[LiveNoiseBenchmarkResult]) -> None:
    fieldnames = list(LiveNoiseBenchmarkResult.__dataclass_fields__)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for result in results:
            writer.writerow(result.__dict__)


def _write_gate_recall_csv(path: Path, results: list[GateRecallBenchmarkResult]) -> None:
    fieldnames = list(GateRecallBenchmarkResult.__dataclass_fields__)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for result in results:
            writer.writerow(result.__dict__)


def _write_markdown(
    path: Path,
    metrics: BenchmarkMetrics,
    results: list[BenchmarkResult],
    *,
    label_set_path: Path,
    evaluator_versions: tuple[str, ...],
) -> None:
    lines = [
        "# Calibration Report",
        "",
        "Generated by `job-agent benchmark` against cached JD snapshots.",
        "",
        f"- Label set: `{_display_path(label_set_path)}`",
        f"- Evaluator: `{', '.join(evaluator_versions) if evaluator_versions else 'not_available'}`",
        "",
        "## Aggregate Metrics",
        "",
        f"- Roles: {metrics.total_roles}",
        (
            "- Exact-recommendation match: "
            f"{metrics.exact_recommendation_matches}/{metrics.total_roles} "
            f"({metrics.exact_recommendation_match_rate:.1%})"
        ),
        (
            "  - Note: `apply_now` vs `consider` is approximate in the deterministic "
            "evaluator because many fit scores cluster near the threshold; fine "
            "ranking is deferred to the LLM evaluator."
        ),
        (
            "- Apply/Consider recall: "
            f"{metrics.apply_consider_recalled}/{metrics.apply_consider_expected} "
            f"({metrics.apply_consider_recall:.1%})"
        ),
        (
            "- Digest precision: "
            f"{metrics.surfaced_correct}/{metrics.surfaced_count} "
            f"({metrics.digest_precision:.1%})"
        ),
        f"- Blocker-detection accuracy: {metrics.blocker_accuracy:.1%}",
        f"- Fit-band agreement: {metrics.fit_band_agreement:.1%}",
        f"- Feasibility correctness: {metrics.feasibility_correctness:.1%}",
        "",
        "## Per-Role Results",
        "",
        (
            "| ID | Company | Role | Expected | Actual | Fit | Feasibility | "
            "Recommendation | Blocker | Fit Band |"
        ),
        "|---|---|---|---|---|---:|---|---|---|---|",
    ]
    for result in results:
        lines.append(
            "| "
            f"{result.role_id} | {result.company} | {result.role_title} | "
            f"{result.expected_recommendation} | {result.actual_recommendation} | "
            f"{result.fit_score} | {_pass_fail(result.feasibility_match)} | "
            f"{_pass_fail(result.recommendation_match)} | "
            f"{_pass_fail(result.blocker_match)} | "
            f"{_pass_fail(result.fit_band_match)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_live_noise_markdown(
    path: Path,
    metrics: LiveNoiseBenchmarkMetrics,
    results: list[LiveNoiseBenchmarkResult],
    *,
    label_set_path: Path,
    label_set_purpose: str,
    evaluator_versions: tuple[str, ...],
) -> None:
    lines = [
        "# Live-Noise Precision Report",
        "",
        "Generated by `job-agent benchmark` when a labelled gate-passer precision set is present.",
        "",
        f"- Label set: `{_display_path(label_set_path)}`",
        f"- Label set purpose: `{label_set_purpose}`",
        f"- Evaluator: `{', '.join(evaluator_versions) if evaluator_versions else 'not_available'}`",
        "",
        "## Aggregate Metrics",
        "",
        f"- Labelled roles: {metrics.labelled_roles}",
        (
            "- Digest precision: "
            f"{metrics.surfaced_correct}/{metrics.surfaced_count} "
            f"({metrics.digest_precision:.1%})"
        ),
        f"- Precision gate: {_pass_fail(metrics.precision_passes)}",
        "",
        "## Per-Role Results",
        "",
        "| ID | Company | Role | Expected | Actual | Fit | Surface |",
        "|---|---|---|---|---|---:|---|",
    ]
    for result in results:
        lines.append(
            "| "
            f"{result.role_id} | {result.company} | {result.role_title} | "
            f"{result.expected_recommendation} | {result.actual_recommendation} | "
            f"{result.fit_score} | {_pass_fail(result.surface_match)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_gate_recall_markdown(
    path: Path,
    metrics: GateRecallBenchmarkMetrics,
    results: list[GateRecallBenchmarkResult],
    label_set_path: Path,
) -> None:
    lines = [
        "# Live-Noise Gate-Recall Report",
        "",
        "Generated by `job-agent benchmark` from the uniform live-noise label set.",
        "",
        f"- Label set: `{_display_path(label_set_path)}`",
        "- Evaluator: `title_department_relevance_gate`",
        "",
        "## Aggregate Metrics",
        "",
        f"- Labelled roles: {metrics.labelled_roles}",
        (
            "- Gate recall: "
            f"{metrics.expected_pass_recalled}/{metrics.expected_pass_count} "
            f"({metrics.gate_recall:.1%})"
        ),
        f"- False skips: {metrics.false_skips}",
        f"- Gate-recall check: {_pass_fail(metrics.recall_passes)}",
        "",
        "## Per-Role Results",
        "",
        "| ID | Company | Role | Expected | Should Pass | Actual Pass | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        lines.append(
            "| "
            f"{result.role_id} | {result.company} | {result.role_title} | "
            f"{result.expected_recommendation} | {result.expected_should_pass_gate} | "
            f"{result.actual_passed_gate} | {result.gate_reason} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _evaluator_versions(results: list[LiveNoiseBenchmarkResult]) -> tuple[str, ...]:
    return tuple(sorted({result.evaluator_version for result in results}))


def _benchmark_evaluator_versions(results: list[BenchmarkResult]) -> tuple[str, ...]:
    return tuple(sorted({result.evaluator_version for result in results}))


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def _company_config(example: dict[str, Any]) -> CompanyConfig:
    tier = int(str(example["expected_strategic_tier"]).removeprefix("tier_"))
    role_id = str(example["id"])
    return CompanyConfig(
        name=str(example["company"]),
        tier=tier,
        enabled=True,
        ats_type="manual",
        source_key=role_id.lower(),
        careers_url=str(example["jd_source"]),
        target_locations=[str(example["location"])],
        target_role_family_notes="Benchmark role family notes are intentionally withheld.",
        warm_path=bool(example.get("warm_path", False)),
    )


def _fetch_source_text(url: str) -> tuple[str, str]:
    try:
        response = httpx.get(
            url,
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "job-search-agent-benchmark/1.0"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return "", f"fetch_failed: {type(exc).__name__}: {exc}"
    text = compact_text(clean_html(response.text))
    if not text:
        return "", f"fetch_empty: HTTP {response.status_code}"
    return text[:MAX_CACHED_CHARS], f"fetched: HTTP {response.status_code}"


def _fallback_snapshot(example: dict[str, Any], status: str) -> str:
    return "\n".join(
        [
            "Cached fallback snapshot because the public source page could not be "
            "converted into stable offline JD text.",
            f"Fetch status: {status}",
            f"Company: {example['company']}",
            f"Role title: {example['role_title']}",
            f"Location: {example['location']}",
            f"Role context: {example['key_reason']}",
        ]
    )


def _cache_document(example: dict[str, Any], text: str, status: str) -> str:
    return "\n".join(
        [
            f"Cached JD snapshot for {example['id']}",
            f"Source URL: {example['jd_source']}",
            f"Fetch status: {status}",
            f"Company: {example['company']}",
            f"Role title: {example['role_title']}",
            f"Location: {example['location']}",
            "",
            text,
            "",
        ]
    )


def _department_hint(title: str, jd_text: str) -> str:
    title_lower = title.lower()
    if "customer success" in title_lower:
        return "Customer Success"
    if "deployment" in title_lower:
        return "Professional Services Operations"
    if "revenue" in title_lower:
        return "Revenue Operations"
    if "product manager" in title_lower:
        return "Product"
    if re.search(r"\b(?:strategy|strategic|business|gtm)\b.*\boperations\b", title_lower):
        return "Strategy & Operations"

    leading_text = jd_text[:1200].lower()
    if re.search(r"\bdepartment:\s*customer success\b", leading_text):
        return "Customer Success"
    if re.search(r"\bdepartment:\s*(?:deployment|professional services)\b", leading_text):
        return "Professional Services Operations"
    return "Strategy & Operations"


def _feasibility_matches(expected: str, actual: str) -> bool:
    return expected == actual


def _fit_band(recommendation: str) -> str:
    if recommendation == "blocked":
        return "blocked"
    if recommendation in APPLY_CONSIDER:
        return "surface"
    return recommendation


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _pass_fail(value: bool) -> str:
    return "pass" if value else "fail"
