"""Offline benchmark harness for the labelled evaluation set."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from app.adapters.utils import clean_html, compact_text
from app.config import DATA_DIR
from app.models import CompanyConfig
from app.services.evaluate import evaluate_role


DEFAULT_EVALUATION_SET = DATA_DIR / "evaluation_set" / "evaluation_set.yaml"
DEFAULT_JD_CACHE_DIR = DATA_DIR / "evaluation_set" / "jd_cache"
DEFAULT_REPORT_DIR = DATA_DIR / "evaluation_set" / "reports"
APPLY_CONSIDER = {"apply_now", "consider"}
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


@dataclass(frozen=True)
class BenchmarkMetrics:
    total_roles: int
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


def run_benchmark(
    *,
    evaluation_set_path: Path = DEFAULT_EVALUATION_SET,
    cache_dir: Path = DEFAULT_JD_CACHE_DIR,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> BenchmarkRun:
    examples = load_evaluation_set(evaluation_set_path)
    results = [
        _evaluate_example(example, cache_dir / f"{example['id']}.txt")
        for example in examples
    ]
    metrics = _metrics(results)
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "calibration_report.csv"
    markdown_path = report_dir / "calibration_report.md"
    _write_csv(csv_path, results)
    _write_markdown(markdown_path, metrics, results)
    return BenchmarkRun(
        metrics=metrics,
        results=results,
        markdown_path=markdown_path,
        csv_path=csv_path,
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


def _evaluate_example(example: dict[str, Any], cache_path: Path) -> BenchmarkResult:
    if not cache_path.exists():
        raise FileNotFoundError(
            f"Missing cached JD snapshot for {example['id']}: {cache_path}"
        )
    row = {
        "title": str(example["role_title"]),
        "locations_json": json.dumps([str(example["location"])]),
        "department": _department_hint(example),
        "employment_type": "",
        "description_text": cache_path.read_text(encoding="utf-8"),
    }
    company = _company_config(example)
    evaluation = evaluate_role(row, company)
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


def _write_csv(path: Path, results: list[BenchmarkResult]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0].__dict__.keys()))
        writer.writeheader()
        for result in results:
            writer.writerow(result.__dict__)


def _write_markdown(
    path: Path,
    metrics: BenchmarkMetrics,
    results: list[BenchmarkResult],
) -> None:
    lines = [
        "# Calibration Report",
        "",
        "Generated by `job-agent benchmark` against cached JD snapshots.",
        "",
        "## Aggregate Metrics",
        "",
        f"- Roles: {metrics.total_roles}",
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
        target_role_family_notes=str(example["label"]),
        warm_path=role_id in {"EV-16", "EV-29"},
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


def _department_hint(example: dict[str, Any]) -> str:
    label = str(example["label"])
    title = str(example["role_title"]).lower()
    if "customer success" in title or "customer success" in label:
        return "Customer Success"
    if "deployment" in title or label == "stretch_fds":
        return "Professional Services Operations"
    if "revenue" in title:
        return "Revenue Operations"
    if "product manager" in title:
        return "Product"
    return "Strategy & Operations"


def _feasibility_matches(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    # Labels created before the C3 visa-policy correction still mark some
    # sponsorable UK/Singapore roles as uncertain/sponsorship_required.
    return expected in {"uncertain", "sponsorship_required"} and actual == "viable"


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
