from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from app.services.benchmark import (
    APPLY_CONSIDER,
    DEFAULT_EVALUATION_SET,
    DEFAULT_JD_CACHE_DIR,
    load_evaluation_set,
    run_gate_recall_benchmark,
    run_benchmark,
    run_live_noise_benchmark,
)
from app.services.llm_evaluator import (
    DEFAULT_CLAUDE_MODEL,
    CachedLLMProvider,
    LLMEvaluationOutput,
    LLMEvaluationResult,
    LLMRoleRequest,
    write_cached_evaluation,
)


class BenchmarkCalibrationTest(unittest.TestCase):
    def test_apply_consider_recall_meets_threshold_offline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = run_benchmark(
                report_dir=Path(directory) / "reports",
                llm_provider=_label_aware_provider(),
            )

        self.assertGreaterEqual(run.metrics.apply_consider_recall, 0.95)
        self.assertTrue(run.metrics.recall_passes)
        self.assertEqual(run.metrics.blocker_accuracy, 1.0)
        self.assertEqual(run.metrics.feasibility_correctness, 1.0)
        self.assertEqual(run.evaluator_versions, ("fake-llm-benchmark",))

    def test_cached_evaluation_set_covers_blocker_cases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = run_benchmark(
                report_dir=Path(directory) / "reports",
                llm_provider=_label_aware_provider(),
            )
        results_by_id = {result.role_id: result for result in run.results}

        for role_id in ("EV-27", "EV-28", "EV-30", "EV-31"):
            with self.subTest(role_id=role_id):
                self.assertTrue((DEFAULT_JD_CACHE_DIR / f"{role_id}.txt").exists())
                self.assertTrue(results_by_id[role_id].actual_blocked)
                self.assertNotIn(
                    results_by_id[role_id].actual_recommendation,
                    APPLY_CONSIDER,
                )

        self.assertEqual(results_by_id["EV-29"].actual_recommendation, "stretch")
        ev31_cache = (DEFAULT_JD_CACHE_DIR / "EV-31.txt").read_text(encoding="utf-8")
        self.assertIn("Security clearance", ev31_cache)
        self.assertIn("continuous residency in the UK for at least 5 years", ev31_cache)

    def test_live_noise_benchmark_reports_precision_from_labelled_sample(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            labels_path = Path(directory) / "live_noise.yaml"
            reports_dir = Path(directory) / "reports"
            labels_path.write_text(
                yaml.safe_dump(
                    {
                        "version": "live_noise_labels_v1",
                        "live_noise_set": [
                            {
                                "id": "LN-001",
                                "company": "ExampleCo",
                                "company_tier": 1,
                                "role_title": "Strategic Operations Lead",
                                "department": "Strategy & Operations",
                                "employment_type": "Full-time",
                                "location": "London, United Kingdom",
                                "source_url": "https://example.com/job",
                                "description_text": (
                                    "Lead strategy and operations programs, own executive "
                                    "cadence, and drive transformation work."
                                ),
                                "expected_recommendation": "apply_now",
                            }
                        ],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            run = run_live_noise_benchmark(
                live_noise_set_path=labels_path,
                report_dir=reports_dir,
                llm_provider=_cached_provider_for_live_noise_example(labels_path, reports_dir),
            )

            self.assertEqual(run.metrics.labelled_roles, 1)
            self.assertEqual(run.metrics.apply_consider_recall, 1.0)
            self.assertEqual(run.metrics.apply_consider_precision, 1.0)
            self.assertEqual(run.metrics.all_surfaced_precision, 1.0)
            self.assertTrue(run.metrics.recall_passes)
            self.assertTrue(run.metrics.passes)
            self.assertTrue(run.markdown_path.exists())
            self.assertTrue(run.csv_path.exists())
            report = run.markdown_path.read_text(encoding="utf-8")
            self.assertIn("Label set purpose: `gate_passer_precision`", report)
            self.assertIn("Apply/Consider recall: 1/1 (100.0%)", report)
            self.assertIn("Apply/Consider precision (gated): 1/1 (100.0%)", report)
            self.assertIn(
                "All-surfaced precision incl. stretch (report-only): 1/1 (100.0%)",
                report,
            )
            self.assertIn("Evaluator:", report)

    def test_live_noise_reports_stretch_precision_without_gating_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            labels_path = Path(directory) / "live_noise.yaml"
            reports_dir = Path(directory) / "reports"
            labels_path.write_text(
                yaml.safe_dump(
                    {
                        "version": "live_noise_labels_v1",
                        "live_noise_set": [
                            {
                                "id": "LN-001",
                                "company": "ExampleCo",
                                "company_tier": 1,
                                "role_title": "Strategic Operations Lead",
                                "department": "Strategy & Operations",
                                "employment_type": "Full-time",
                                "location": "London, United Kingdom",
                                "source_url": "https://example.com/job",
                                "description_text": "Lead strategy and operations work.",
                                "expected_recommendation": "apply_now",
                            },
                            {
                                "id": "LN-002",
                                "company": "ExampleCo",
                                "company_tier": 1,
                                "role_title": "Ambiguous Transformation Lead",
                                "department": "Business Programs",
                                "employment_type": "Full-time",
                                "location": "London, United Kingdom",
                                "source_url": "https://example.com/stretch-noise",
                                "description_text": "Customer-facing deployment strategy work.",
                                "expected_recommendation": "skip",
                            },
                            {
                                "id": "LN-003",
                                "company": "ExampleCo",
                                "company_tier": 1,
                                "role_title": "Adjacent Transformation Lead",
                                "department": "Business Programs",
                                "employment_type": "Full-time",
                                "location": "London, United Kingdom",
                                "source_url": "https://example.com/stretch",
                                "description_text": "Customer-facing deployment strategy work.",
                                "expected_recommendation": "stretch",
                            },
                        ],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            cache_dir = reports_dir / "llm_cache"
            examples = yaml.safe_load(labels_path.read_text(encoding="utf-8"))[
                "live_noise_set"
            ]
            for example, score in zip(examples, (88, 65, 65), strict=True):
                write_cached_evaluation(
                    cache_dir=cache_dir,
                    model=DEFAULT_CLAUDE_MODEL,
                    row={
                        "title": str(example["role_title"]),
                        "locations_json": "[\"London, United Kingdom\"]",
                        "department": str(example.get("department") or ""),
                        "employment_type": str(example.get("employment_type") or ""),
                        "description_text": str(example.get("description_text") or ""),
                        "source_url": str(example.get("source_url") or ""),
                    },
                    output=_output(score),
                )

            run = run_live_noise_benchmark(
                live_noise_set_path=labels_path,
                report_dir=reports_dir,
                llm_provider=CachedLLMProvider(cache_dir=cache_dir),
            )

            self.assertEqual(run.metrics.apply_consider_precision, 1.0)
            self.assertEqual(run.metrics.all_surfaced_precision, 2 / 3)
            self.assertTrue(run.metrics.precision_passes)
            self.assertTrue(run.metrics.passes)
            report = run.markdown_path.read_text(encoding="utf-8")
            self.assertIn("Apply/Consider precision (gated): 1/1 (100.0%)", report)
            self.assertIn(
                "All-surfaced precision incl. stretch (report-only): 2/3 (66.7%)",
                report,
            )

    def test_live_noise_benchmark_fails_when_precision_hides_recall_miss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            labels_path = Path(directory) / "live_noise.yaml"
            reports_dir = Path(directory) / "reports"
            labels_path.write_text(
                yaml.safe_dump(
                    {
                        "version": "live_noise_labels_v1",
                        "live_noise_set": [
                            {
                                "id": "LN-001",
                                "company": "ExampleCo",
                                "company_tier": 1,
                                "role_title": "Strategic Operations Lead",
                                "department": "Strategy & Operations",
                                "employment_type": "Full-time",
                                "location": "London, United Kingdom",
                                "source_url": "https://example.com/job",
                                "description_text": (
                                    "Lead strategy and operations programs, own executive "
                                    "cadence, and drive transformation work."
                                ),
                                "expected_recommendation": "apply_now",
                            },
                            {
                                "id": "LN-002",
                                "company": "ExampleCo",
                                "company_tier": 1,
                                "role_title": "Customer Transformation Lead",
                                "department": "Business Programs",
                                "employment_type": "Full-time",
                                "location": "London, United Kingdom",
                                "source_url": "https://example.com/job-two",
                                "description_text": "Ambiguous role with insufficient signal.",
                                "expected_recommendation": "consider",
                            },
                        ],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            cache_dir = reports_dir / "llm_cache"
            examples = yaml.safe_load(labels_path.read_text(encoding="utf-8"))[
                "live_noise_set"
            ]
            for example, score in zip(examples, (88, 35), strict=True):
                write_cached_evaluation(
                    cache_dir=cache_dir,
                    model=DEFAULT_CLAUDE_MODEL,
                    row={
                        "title": str(example["role_title"]),
                        "locations_json": "[\"London, United Kingdom\"]",
                        "department": str(example.get("department") or ""),
                        "employment_type": str(example.get("employment_type") or ""),
                        "description_text": str(example.get("description_text") or ""),
                        "source_url": str(example.get("source_url") or ""),
                    },
                    output=_output(score),
                )

            run = run_live_noise_benchmark(
                live_noise_set_path=labels_path,
                report_dir=reports_dir,
                llm_provider=CachedLLMProvider(cache_dir=cache_dir),
            )

            self.assertEqual(run.metrics.apply_consider_precision, 1.0)
            self.assertEqual(run.metrics.all_surfaced_precision, 1.0)
            self.assertEqual(run.metrics.apply_consider_recall, 0.5)
            self.assertTrue(run.metrics.precision_passes)
            self.assertFalse(run.metrics.recall_passes)
            self.assertFalse(run.metrics.passes)

    def test_gate_recall_benchmark_uses_uniform_label_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            labels_path = Path(directory) / "live_noise.yaml"
            reports_dir = Path(directory) / "reports"
            labels_path.write_text(
                yaml.safe_dump(
                    {
                        "version": "live_noise_labels_v1",
                        "set_purpose": "uniform_gate_recall",
                        "live_noise_set": [
                            {
                                "id": "LN-001",
                                "company": "ExampleCo",
                                "company_tier": 1,
                                "role_title": "Strategic Operations Lead",
                                "department": "Strategy & Operations",
                                "employment_type": "Full-time",
                                "location": "London, United Kingdom",
                                "source_url": "https://example.com/job",
                                "description_text": (
                                    "Lead strategy and operations programs, own executive "
                                    "cadence, and drive transformation work."
                                ),
                                "expected_recommendation": "apply_now",
                            },
                            {
                                "id": "LN-002",
                                "company": "ExampleCo",
                                "company_tier": 1,
                                "role_title": "Payroll Manager",
                                "department": "Finance",
                                "employment_type": "Full-time",
                                "location": "London, United Kingdom",
                                "source_url": "https://example.com/payroll",
                                "description_text": "Own payroll operations.",
                                "expected_recommendation": "skip",
                            },
                        ],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            run = run_gate_recall_benchmark(
                live_noise_set_path=labels_path,
                report_dir=reports_dir,
            )

            self.assertEqual(run.metrics.labelled_roles, 2)
            self.assertEqual(run.metrics.expected_pass_count, 1)
            self.assertEqual(run.metrics.gate_recall, 1.0)
            report = run.markdown_path.read_text(encoding="utf-8")
            self.assertIn("Evaluator: `title_department_relevance_gate`", report)

class LabelAwareProvider:
    model_version = "fake-llm-benchmark"

    def __init__(self, labels: dict[str, str]) -> None:
        self.labels = labels

    def evaluate(self, request: LLMRoleRequest) -> LLMEvaluationResult:
        role_id = request.company.source_key.upper()
        expected = self.labels.get(role_id, "skip")
        if expected in APPLY_CONSIDER:
            output = _output(88)
        elif expected == "stretch":
            output = _output(55)
        else:
            output = _output(35)
        return LLMEvaluationResult(
            output=output,
            model_version=self.model_version,
            prompt_version="test_prompt_v1",
            cache_hit=True,
        )


def _label_aware_provider() -> LabelAwareProvider:
    labels = {
        str(example["id"]).upper(): str(example["expected_recommendation"])
        for example in load_evaluation_set(DEFAULT_EVALUATION_SET)
    }
    return LabelAwareProvider(labels)


def _cached_provider_for_live_noise_example(
    labels_path: Path,
    reports_dir: Path,
) -> CachedLLMProvider:
    cache_dir = reports_dir / "llm_cache"
    example = yaml.safe_load(labels_path.read_text(encoding="utf-8"))["live_noise_set"][0]
    row = {
        "title": str(example["role_title"]),
        "locations_json": "[\"London, United Kingdom\"]",
        "department": str(example.get("department") or ""),
        "employment_type": str(example.get("employment_type") or ""),
        "description_text": str(example.get("description_text") or ""),
        "source_url": str(example.get("source_url") or ""),
    }
    write_cached_evaluation(
        cache_dir=cache_dir,
        model=DEFAULT_CLAUDE_MODEL,
        row=row,
        output=_output(88),
    )
    return CachedLLMProvider(cache_dir=cache_dir)


def _output(score: int) -> LLMEvaluationOutput:
    return LLMEvaluationOutput.model_validate(
        {
            "role_family_fit": score,
            "evidence_strength": score,
            "scope_seniority": score,
            "gap_manageability": score,
            "confidence": 0.82,
            "advisory_recommendation": "consider" if score >= 65 else "skip",
            "alignments": [
                {
                    "job_requirement": "Lead strategy operations programs",
                    "candidate_evidence": "Google transformation work",
                    "evidence_strength": "strong" if score >= 65 else "weak",
                }
            ],
            "gaps": [
                {
                    "gap": "Benchmark fixture gap",
                    "severity": "medium",
                    "mitigation": "Use cached real Claude outputs for production benchmark",
                }
            ],
            "hard_blockers": [],
            "uncertainties": [],
            "summary": "Benchmark fixture output.",
        }
    )


if __name__ == "__main__":
    unittest.main()
