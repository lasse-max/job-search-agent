from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from app.services.benchmark import (
    APPLY_CONSIDER,
    DEFAULT_EVALUATION_SET,
    DEFAULT_JD_CACHE_DIR,
    _fallback_snapshot,
    load_evaluation_set,
    populate_benchmark_llm_cache,
    run_gate_recall_benchmark,
    run_benchmark,
    run_live_noise_benchmark,
)
from app.services.llm_evaluator import (
    DEFAULT_CLAUDE_MODEL,
    CachedLLMProvider,
    LLMEvaluationOutput,
    LLMEvaluationResult,
    LLMProviderError,
    LLMRoleRequest,
    ModelSpendCapExceeded,
    write_cached_evaluation,
)


class BenchmarkCalibrationTest(unittest.TestCase):
    def test_authoritative_evaluation_set_rejects_malformed_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "malformed-evaluation-set.yaml"
            path.write_text(
                "evaluation_set:\n"
                "  - id: EV-BAD\n"
                "    key_reason: strategy: malformed authoritative YAML\n",
                encoding="utf-8",
            )

            with self.assertRaises(yaml.YAMLError) as raised:
                load_evaluation_set(path)

        self.assertIn(str(path), str(raised.exception))
        self.assertIn("line 3", str(raised.exception))

    def test_fallback_snapshots_and_committed_fixtures_do_not_leak_labels(self) -> None:
        sentinel = "LABEL-DERIVED KEY REASON MUST NOT REACH JD TEXT"
        snapshot = _fallback_snapshot(
            {
                "company": "Example Co",
                "role_title": "Strategy Lead",
                "location": "London",
                "key_reason": sentinel,
            },
            "fetch_failed: fixture",
        )

        self.assertNotIn(sentinel, snapshot)
        self.assertNotIn("Role context:", snapshot)
        examples_by_id = {
            str(example["id"]): example for example in load_evaluation_set(DEFAULT_EVALUATION_SET)
        }
        for role_id in ("EV-01", "EV-04", "EV-10", "EV-12", "EV-22", "EV-29"):
            with self.subTest(role_id=role_id):
                cache_text = (DEFAULT_JD_CACHE_DIR / f"{role_id}.txt").read_text(
                    encoding="utf-8"
                )
                self.assertNotIn("Role context:", cache_text)
                self.assertNotIn(str(examples_by_id[role_id]["key_reason"]), cache_text)

    def test_population_retries_one_malformed_role_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = {"evaluation_set": [load_evaluation_set(DEFAULT_EVALUATION_SET)[0]]}
            evaluation_set = root / "evaluation_set.yaml"
            evaluation_set.write_text(
                yaml.safe_dump(source, sort_keys=False),
                encoding="utf-8",
            )
            cache_dir = root / "jd_cache"
            cache_dir.mkdir()
            (cache_dir / "EV-01.txt").write_text(
                (DEFAULT_JD_CACHE_DIR / "EV-01.txt").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            provider = FailOnceProvider()

            run = run_benchmark(
                evaluation_set_path=evaluation_set,
                cache_dir=cache_dir,
                report_dir=root / "reports",
                llm_provider=provider,
            )

            self.assertEqual(provider.calls, 2)
            self.assertEqual(len(run.results), 1)

    def test_population_does_not_retry_non_output_provider_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = {"evaluation_set": [load_evaluation_set(DEFAULT_EVALUATION_SET)[0]]}
            evaluation_set = root / "evaluation_set.yaml"
            evaluation_set.write_text(
                yaml.safe_dump(source, sort_keys=False),
                encoding="utf-8",
            )
            cache_dir = root / "jd_cache"
            cache_dir.mkdir()
            (cache_dir / "EV-01.txt").write_text(
                (DEFAULT_JD_CACHE_DIR / "EV-01.txt").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            provider = NonRetryableProvider()

            with self.assertRaises(LLMProviderError):
                run_benchmark(
                    evaluation_set_path=evaluation_set,
                    cache_dir=cache_dir,
                    report_dir=root / "reports",
                    llm_provider=provider,
                )

            self.assertEqual(provider.calls, 1)

    def test_population_continues_after_twice_malformed_role(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            examples = load_evaluation_set(DEFAULT_EVALUATION_SET)[:2]
            evaluation_set = root / "evaluation_set.yaml"
            evaluation_set.write_text(
                yaml.safe_dump({"evaluation_set": examples}, sort_keys=False),
                encoding="utf-8",
            )
            cache_dir = root / "jd_cache"
            cache_dir.mkdir()
            for example in examples:
                role_id = str(example["id"])
                (cache_dir / f"{role_id}.txt").write_text(
                    (DEFAULT_JD_CACHE_DIR / f"{role_id}.txt").read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            provider = FailNamedRoleProvider(str(examples[0]["role_title"]))

            failures = populate_benchmark_llm_cache(
                llm_provider=provider,
                evaluation_set_path=evaluation_set,
                cache_dir=cache_dir,
                live_noise_set_path=root / "missing-live-set.yaml",
            )

            self.assertEqual([failure.role_id for failure in failures], [examples[0]["id"]])
            self.assertEqual(provider.calls.count(str(examples[0]["role_title"])), 2)
            self.assertEqual(provider.calls.count(str(examples[1]["role_title"])), 1)

    def test_retry_charges_both_paid_attempts_and_rechecks_cap(self) -> None:
        for cap, expected_calls, expected_error, expected_spend in (
            ("0.008", 2, None, 0.008),
            ("0.007", 1, ModelSpendCapExceeded, 0.004),
        ):
            with self.subTest(cap=cap), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = {"evaluation_set": [load_evaluation_set(DEFAULT_EVALUATION_SET)[0]]}
                evaluation_set = root / "evaluation_set.yaml"
                evaluation_set.write_text(
                    yaml.safe_dump(source, sort_keys=False),
                    encoding="utf-8",
                )
                cache_dir = root / "jd_cache"
                cache_dir.mkdir()
                (cache_dir / "EV-01.txt").write_text(
                    (DEFAULT_JD_CACHE_DIR / "EV-01.txt").read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                ledger = root / "spend.json"
                provider = PaidFailThenSuccessProvider()
                environment = {
                    "MODEL_SPEND_LEDGER_PATH": str(ledger),
                    "MONTHLY_MODEL_SPEND_CAP_USD": cap,
                    "MODEL_EVAL_ESTIMATED_COST_USD": "0.004",
                }

                with patch.dict(os.environ, environment, clear=False):
                    if expected_error is None:
                        run_benchmark(
                            evaluation_set_path=evaluation_set,
                            cache_dir=cache_dir,
                            report_dir=root / "reports",
                            llm_provider=provider,
                        )
                    else:
                        with self.assertRaises(expected_error):
                            run_benchmark(
                                evaluation_set_path=evaluation_set,
                                cache_dir=cache_dir,
                                report_dir=root / "reports",
                                llm_provider=provider,
                            )

                spend = sum(json.loads(ledger.read_text(encoding="utf-8")).values())
                self.assertEqual(provider.calls, expected_calls)
                self.assertAlmostEqual(spend, expected_spend, places=6)

    def test_apply_consider_recall_meets_threshold_offline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = run_benchmark(
                report_dir=Path(directory) / "reports",
            )

        self.assertGreaterEqual(run.metrics.apply_consider_recall, 0.95)
        self.assertTrue(run.metrics.recall_passes)
        self.assertEqual(run.metrics.blocker_accuracy, 1.0)
        self.assertEqual(run.metrics.feasibility_correctness, 1.0)
        self.assertEqual(
            run.evaluator_versions,
            (
                "hybrid_claude_v4; prompt=role_evaluation_v6; "
                "model=claude-haiku-4-5",
            ),
        )

    def test_cached_evaluation_set_covers_blocker_cases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = run_benchmark(
                report_dir=Path(directory) / "reports",
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

    def test_committed_live_noise_cache_meets_recall_and_precision_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = run_live_noise_benchmark(report_dir=Path(directory) / "reports")

        self.assertEqual(run.metrics.labelled_roles, 150)
        self.assertGreaterEqual(run.metrics.apply_consider_recall, 0.90)
        self.assertGreaterEqual(run.metrics.apply_consider_precision, 0.80)
        self.assertTrue(run.metrics.passes)
        results_by_id = {result.role_id: result for result in run.results}
        for role_id in ("LNP-020", "LNP-030", "LNP-150"):
            with self.subTest(role_id=role_id):
                self.assertTrue(results_by_id[role_id].expected_blocked)
                self.assertTrue(results_by_id[role_id].actual_blocked)
                self.assertTrue(results_by_id[role_id].blocker_match)
        self.assertEqual(run.metrics.blocker_expected_positives, 3)
        self.assertEqual(run.metrics.blocker_positives_recalled, 3)
        self.assertEqual(run.metrics.blocker_recall, 1.0)
        for role_id in ("LNP-052", "LNP-060"):
            with self.subTest(role_id=role_id):
                self.assertIn(results_by_id[role_id].estimated_level, {"L6", "L7+"})
        for role_id in ("LNP-056", "LNP-094", "LNP-141"):
            with self.subTest(role_id=role_id):
                self.assertIn(results_by_id[role_id].estimated_level, {"L3", "unknown"})
        self.assertTrue(
            all(
                not re.search(
                    r"\b(?:the\s+)?candidate(?:'s)?\b",
                    result.level_rationale,
                    flags=re.IGNORECASE,
                )
                for result in run.results
            )
        )
        self.assertEqual(
            run.evaluator_versions,
            (
                "hybrid_claude_v4; prompt=role_evaluation_v6; "
                "model=claude-haiku-4-5",
            ),
        )

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


class FailOnceProvider:
    model_version = "fake-retry-provider"

    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, request: LLMRoleRequest) -> LLMEvaluationResult:
        self.calls += 1
        if self.calls == 1:
            raise LLMProviderError(
                "claude_tool_input_validation_failed: gaps missing",
                retryable_output=True,
            )
        return LLMEvaluationResult(
            output=_output(88),
            model_version=self.model_version,
            prompt_version="test_prompt_v1",
            cache_hit=False,
        )


class NonRetryableProvider:
    model_version = "fake-auth-failure"

    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, request: LLMRoleRequest) -> LLMEvaluationResult:
        self.calls += 1
        raise LLMProviderError("claude_evaluation_failed: HTTP 401")


class FailNamedRoleProvider:
    model_version = "fake-continue-provider"

    def __init__(self, failing_title: str) -> None:
        self.failing_title = failing_title
        self.calls: list[str] = []

    def evaluate(self, request: LLMRoleRequest) -> LLMEvaluationResult:
        title = str(request.row["title"])
        self.calls.append(title)
        if title == self.failing_title:
            raise LLMProviderError(
                "claude_tool_input_validation_failed: gaps missing",
                retryable_output=True,
            )
        return LLMEvaluationResult(
            output=_output(88),
            model_version=self.model_version,
            prompt_version="test_prompt_v1",
            cache_hit=False,
        )


class PaidFailThenSuccessProvider:
    model_version = "fake-paid-retry"

    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, request: LLMRoleRequest) -> LLMEvaluationResult:
        self.calls += 1
        if self.calls == 1:
            raise LLMProviderError(
                "claude_tool_input_validation_failed: gaps missing",
                retryable_output=True,
                cost_usd=0.004,
            )
        return LLMEvaluationResult(
            output=_output(88),
            model_version=self.model_version,
            prompt_version="test_prompt_v1",
            cost_usd=0.004,
            cache_hit=False,
        )


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
            "estimated_level": "L5",
            "level_confidence": 75,
            "level_rationale": "Benchmark fixture models an in-band senior IC role.",
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
