from pathlib import Path
import unittest

import yaml


class SpendWorkflowTest(unittest.TestCase):
    def test_monthly_ledger_survives_success_failure_and_serializes_scans(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = yaml.safe_load((root / ".github/workflows/scan.yml").read_text())
        self.assertEqual(workflow["concurrency"], {
            "group": "scheduled-scan", "cancel-in-progress": False,
        })
        steps = workflow["jobs"]["scan"]["steps"]
        restore = next(s for s in steps if s.get("id") == "model-spend")
        scan = next(s for s in steps if s.get("run") == "job-agent scan-all")
        save = next(s for s in steps if s.get("uses") == "actions/cache/save@v4")
        prepare = next(s for s in steps if s.get("id") == "scan-budget")
        self.assertEqual(scan["env"]["MONTHLY_MODEL_SPEND_CAP_USD"],
                         "${{ steps.scan-budget.outputs.monthly_cap_usd }}")
        self.assertEqual(prepare["run"], "python scripts/prepare_scan_budget.py")
        self.assertLess(steps.index(restore), steps.index(prepare))
        self.assertLess(steps.index(prepare), steps.index(scan))
        self.assertEqual(prepare["env"]["RECONCILED_MTD_USD"], "${{ inputs.reconciled_mtd_usd }}")
        self.assertEqual(prepare["env"]["RECONCILED_AS_OF"], "${{ inputs.reconciled_as_of }}")
        self.assertIn("inputs.full_stale_backfill", prepare["env"]["FULL_STALE_BACKFILL"])
        self.assertNotIn("continue-on-error", prepare)
        self.assertLess(steps.index(restore), steps.index(scan))
        self.assertLess(steps.index(scan), steps.index(save))
        self.assertEqual(restore["uses"], "actions/cache/restore@v4")
        # Do not change this path: Actions includes it in the opaque cache version.
        self.assertEqual(restore["with"]["path"], "data/model_spend_ledger.json")
        self.assertEqual(save["with"]["path"], restore["with"]["path"])
        self.assertEqual(save["with"]["key"], restore["with"]["key"])
        self.assertTrue(restore["with"]["key"].startswith(
            restore["with"]["restore-keys"].strip()
        ))
        self.assertIn("github.run_id", save["with"]["key"])
        self.assertIn("github.run_attempt", save["with"]["key"])
        self.assertIn("always()", save["if"])
        receipt_restore = next(s for s in steps if s.get("id") == "model-spend-reconciliation")
        receipt_save = next(s for s in steps if s.get("name") == "Save model spend reconciliation proof")
        self.assertEqual(receipt_restore["with"]["path"], "data/model_spend_reconciliation.json")
        self.assertEqual(receipt_restore["with"], receipt_save["with"] | {
            "restore-keys": "job-agent-spend-reconciliation-v1-\n",
        })
        self.assertIn("always()", receipt_save["if"])
        warning = next(s for s in steps if s.get("name", "").startswith("Warn when prior"))
        self.assertIn("cache-matched-key == ''", warning["if"])
        self.assertIn("::warning", warning["run"])
        artifact = next(s for s in steps if s.get("uses") == "actions/upload-artifact@v4")
        self.assertIn("data/model_spend_ledger.json", artifact["with"]["path"])
        self.assertIn("data/model_spend_reconciliation.json", artifact["with"]["path"])
        self.assertEqual(artifact["if"], "always()")
