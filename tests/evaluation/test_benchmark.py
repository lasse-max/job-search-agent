from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from app.services.benchmark import (
    APPLY_CONSIDER,
    DEFAULT_JD_CACHE_DIR,
    run_gate_recall_benchmark,
    run_benchmark,
    run_live_noise_benchmark,
)


class BenchmarkCalibrationTest(unittest.TestCase):
    def test_apply_consider_recall_meets_threshold_offline(self) -> None:
        run = run_benchmark()

        self.assertGreaterEqual(run.metrics.apply_consider_recall, 0.95)
        self.assertTrue(run.metrics.recall_passes)
        self.assertEqual(run.metrics.exact_recommendation_matches, 22)
        self.assertEqual(run.metrics.blocker_accuracy, 1.0)
        self.assertEqual(run.metrics.feasibility_correctness, 1.0)

    def test_cached_evaluation_set_covers_blocker_cases(self) -> None:
        run = run_benchmark()
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
            )

            self.assertEqual(run.metrics.labelled_roles, 1)
            self.assertEqual(run.metrics.digest_precision, 1.0)
            self.assertTrue(run.markdown_path.exists())
            self.assertTrue(run.csv_path.exists())
            report = run.markdown_path.read_text(encoding="utf-8")
            self.assertIn("Label set purpose: `gate_passer_precision`", report)
            self.assertIn("Evaluator:", report)

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


if __name__ == "__main__":
    unittest.main()
