from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from app.config import CONFIG_DIR, load_recency_policy
from app.services.llm_evaluator import ModelSpendTracker
from app.services.scan_budget import ScanBudget


class ScanBudgetTest(unittest.TestCase):
    def test_deadline_is_inclusive_and_cannot_restart_after_expiry(self):
        readings = iter((10.0, 16209.0, 16210.0, 0.0))
        budget = ScanBudget.start(clock=lambda: next(readings))
        self.assertFalse(budget.expired())
        self.assertTrue(budget.expired())
        self.assertTrue(budget.expired())

    def test_budget_config_is_required_positive_integer_below_job_timeout(self):
        raw = yaml.safe_load((CONFIG_DIR / "recency_policy.yaml").read_text())
        with tempfile.TemporaryDirectory() as directory:
            for index, value in enumerate((None, True, False, 0, -1, 1.5, "270", 330, 360)):
                with self.subTest(value=value):
                    path = Path(directory) / f"config-{index}.yaml"
                    path.write_text(yaml.safe_dump(raw | {"backfill_wall_clock_budget_minutes": value}))
                    with self.assertRaisesRegex(ValueError, "backfill_wall_clock_budget_minutes"):
                        load_recency_policy(path)

    def test_failed_atomic_ledger_replace_preserves_previous_paid_total(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spend.json"
            tracker = ModelSpendTracker(path)
            tracker.record(7.0)
            original = path.read_bytes()
            with patch("app.services.llm_evaluator.os.replace", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    tracker.record(0.001)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(path.parent.iterdir()), [path])
            tracker.record(0.001)
            self.assertAlmostEqual(tracker.current_month_spend(), 7.001)
