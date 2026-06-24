from __future__ import annotations

import unittest

from app.services.benchmark import APPLY_CONSIDER, DEFAULT_JD_CACHE_DIR, run_benchmark


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


if __name__ == "__main__":
    unittest.main()
