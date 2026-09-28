from datetime import date
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.services.llm_evaluator import ModelSpendCapExceeded, ModelSpendTracker
from scripts.prepare_scan_budget import BudgetSetupError, main, monthly_cap, prepare_budget


class ScanBudgetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.config = root / "budget.yaml"
        self.ledger = root / "ledger.json"
        self.receipt = root / "receipt.json"
        self.config.write_text(
            'default_monthly_cap_usd: 30\nmonth_overrides: {"2026-09": 40}\n',
        )

    def prepare(self, **changes: object) -> dict:
        args = {
            "config_path": self.config, "ledger_path": self.ledger,
            "receipt_path": self.receipt, "today": date(2026, 9, 28),
            "run_id": "123", "run_attempt": 1, "full_backfill": True,
            "reconciled_mtd": "11.63", "reconciled_as_of": "2026-09-28",
        }
        return prepare_budget(**(args | changes))

    def test_reconciliation_replaces_current_month_preserves_others_and_enforces_cap(self) -> None:
        self.ledger.write_text(json.dumps({"2026-08": 17, "2026-09": 5}))
        result = self.prepare()
        self.assertEqual(json.loads(self.ledger.read_text()), {"2026-08": 17, "2026-09": 11.63})
        self.assertTrue(result["replaced_ledger_value"])
        self.assertEqual(result["monthly_cap_usd"], 40)
        tracker = ModelSpendTracker(self.ledger, monthly_cap_usd=result["monthly_cap_usd"])
        with patch("app.services.llm_evaluator._current_month", return_value="2026-09"):
            tracker.record(28.37)
            self.assertEqual(tracker.current_month_spend(), 40)
            with self.assertRaises(ModelSpendCapExceeded):
                tracker.assert_budget_allows()

    def test_month_override_expires_in_october(self) -> None:
        self.assertEqual(monthly_cap(self.config, date(2026, 9, 30)), 40)
        self.assertEqual(monthly_cap(self.config, date(2026, 10, 1)), 30)

    def test_rerun_and_duplicate_step_never_reset_post_seed_spend(self) -> None:
        self.prepare()
        self.ledger.write_text(json.dumps({"2026-09": 15.21}))
        for attempt in (1, 2, 3):
            with self.subTest(attempt=attempt):
                result = self.prepare(run_attempt=attempt)
                self.assertFalse(result["replaced_ledger_value"])
                self.assertEqual(result["tracked_mtd_usd"], 15.21)
                self.assertEqual(json.loads(self.ledger.read_text())["2026-09"], 15.21)

    def test_rerun_without_its_receipt_cannot_seed(self) -> None:
        self.ledger.write_text(json.dumps({"2026-09": 15.21}))
        for receipt in ({}, {"run_id": "different-run", "amount_usd": 11.63}):
            self.receipt.write_text(json.dumps(receipt))
            with self.subTest(receipt=receipt), self.assertRaisesRegex(BudgetSetupError, "Rerun"):
                self.prepare(run_attempt=2)
            self.assertEqual(json.loads(self.ledger.read_text())["2026-09"], 15.21)

    def test_full_backfill_requires_current_proof_even_with_a_numeric_ledger(self) -> None:
        self.ledger.write_text(json.dumps({"2026-09": 11.63}))
        with self.assertRaisesRegex(BudgetSetupError, "requires today's"):
            self.prepare(reconciled_mtd="", reconciled_as_of="")
        self.prepare()
        result = self.prepare(reconciled_mtd="", reconciled_as_of="", run_id="124")
        self.assertTrue(result["reconciled_today"])
        self.assertFalse(result["replaced_ledger_value"])
        with self.assertRaisesRegex(BudgetSetupError, "requires today's"):
            self.prepare(
                reconciled_mtd="", reconciled_as_of="", run_id="124", today=date(2026, 9, 29),
            )
        self.ledger.write_text(json.dumps({"2026-09": 0}))
        with self.assertRaisesRegex(BudgetSetupError, "requires today's"):
            self.prepare(reconciled_mtd="", reconciled_as_of="", run_attempt=2)

    def test_missing_partial_nonfinite_negative_and_stale_inputs_fail_without_writes(self) -> None:
        cases = [
            {"reconciled_mtd": ""}, {"reconciled_as_of": ""},
            {"reconciled_as_of": "2026-09-27"}, {"reconciled_as_of": "2026-08-28"},
            {"reconciled_as_of": "2026-9-28"}, {"reconciled_as_of": "2026-09-29"},
            {"reconciled_as_of": "2026-09-28T00:00:00Z"},
            *[{"reconciled_mtd": value} for value in ("nan", "inf", "-inf", "-1", "bad")],
        ]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(BudgetSetupError):
                self.prepare(**changes)
            self.assertFalse(self.ledger.exists())
            self.assertFalse(self.receipt.exists())
        self.assertEqual(self.prepare(reconciled_mtd="0")["tracked_mtd_usd"], 0)

    def test_normal_scheduled_scan_needs_no_seed_and_does_not_change_ledger(self) -> None:
        result = self.prepare(full_backfill=False, reconciled_mtd="", reconciled_as_of="")
        self.assertFalse(result["reconciled_today"])
        self.assertFalse(self.ledger.exists())
        self.assertEqual(result["monthly_cap_usd"], 40)

    def test_invalid_caps_or_cached_amounts_fail_loud(self) -> None:
        for config in (
            "default_monthly_cap_usd: .nan", "default_monthly_cap_usd: -1",
            "default_monthly_cap_usd: 0", "default_monthly_cap_usd: true",
            'default_monthly_cap_usd: 30\nmonth_overrides: {"2026-13": 40}',
            'default_monthly_cap_usd: 30\nmonth_overrides: {"2026-09": .inf}',
        ):
            self.config.write_text(config)
            with self.subTest(config=config), self.assertRaises(BudgetSetupError):
                self.prepare()
        self.config.write_text("default_monthly_cap_usd: 30")
        self.ledger.write_text('{"2026-09": "nan"}')
        with self.assertRaises(BudgetSetupError):
            self.prepare()

    def test_entrypoint_exports_validated_cap_and_reports_guard_failures(self) -> None:
        output_path = Path(self.directory.name) / "github-output"
        with patch("scripts.prepare_scan_budget.prepare_budget", return_value={
            "monthly_cap_usd": 40, "tracked_mtd_usd": 11.63,
        }), patch.dict("os.environ", {"GITHUB_OUTPUT": str(output_path)}), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)
        self.assertEqual(output_path.read_text(), "monthly_cap_usd=40\n")
        output = io.StringIO()
        with patch("scripts.prepare_scan_budget.prepare_budget", side_effect=BudgetSetupError(
            "Full backfill requires today's reconciled MTD and retained ledger proof.",
        )), redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertIn("::error", output.getvalue())
        self.assertEqual(output_path.read_text(), "monthly_cap_usd=40\n")
        output = io.StringIO()
        with patch("scripts.prepare_scan_budget.prepare_budget", side_effect=OSError(
            "private-secret-path",
        )), redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertNotIn("private-secret", output.getvalue())
