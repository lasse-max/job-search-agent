from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


class SpendWorkflowTest(unittest.TestCase):
    def test_time_budget_leaves_headroom_for_cleanup_before_runner_limit(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = yaml.safe_load((root / ".github/workflows/scan.yml").read_text())
        recency = yaml.safe_load((root / "config/recency_policy.yaml").read_text())
        job = workflow["jobs"]["scan"]
        scan = next(step for step in job["steps"] if step.get("run") == "job-agent scan-all")
        self.assertEqual(recency["backfill_wall_clock_budget_minutes"], 270)
        self.assertEqual(job["timeout-minutes"], 330)
        self.assertLess(recency["backfill_wall_clock_budget_minutes"], scan["timeout-minutes"])
        self.assertLess(scan["timeout-minutes"], job["timeout-minutes"])
        self.assertLess(job["timeout-minutes"], 360)

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
        self.assertEqual(scan["env"]["MONTHLY_MODEL_SPEND_CAP_USD"], "30")
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
        warning = next(s for s in steps if s.get("name", "").startswith("Warn when prior"))
        self.assertIn("cache-matched-key == ''", warning["if"])
        self.assertIn("::warning", warning["run"])
        artifact = next(s for s in steps if s.get("uses") == "actions/upload-artifact@v4")
        self.assertIn("data/model_spend_ledger.json", artifact["with"]["path"])
        self.assertEqual(artifact["if"], "always()")

    def test_full_backfill_dispatch_has_no_seed_or_reconciliation_prerequisite(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = yaml.safe_load((root / ".github/workflows/scan.yml").read_text())
        # PyYAML's YAML 1.1 parser reads the Actions "on" key as True.
        triggers = workflow.get("on", workflow.get(True))
        inputs = triggers["workflow_dispatch"]["inputs"]
        self.assertEqual(set(inputs), {"full_stale_backfill"})
        self.assertEqual(inputs["full_stale_backfill"]["type"], "boolean")
        self.assertFalse(inputs["full_stale_backfill"]["required"])
        job = workflow["jobs"]["scan"]
        self.assertNotIn("if", job)
        steps = job["steps"]
        scan = next(step for step in steps if step.get("run") == "job-agent scan-all")
        self.assertNotIn("if", scan)
        self.assertEqual(scan["env"]["STALE_EVALUATION_BACKFILL_LIMIT"],
                         "${{ inputs.full_stale_backfill && '10000' || '25' }}")
        # A newly added seed-validator step must fail this regression, not silently
        # become a prerequisite for the owner's already-approved dispatch.
        preceding_commands = [step for step in steps[:steps.index(scan)] if "run" in step]
        self.assertEqual({step["name"] for step in preceding_commands}, {
            "Warn when prior tracked spend is unavailable", "Install project",
            "Snapshot retained model spend before scan",
        })
        warning = next(step for step in preceding_commands if step["name"].startswith("Warn"))
        self.assertTrue(warning["run"].startswith('echo "::warning'))
        self.assertNotIn("exit 1", warning["run"])
        self.assertNotIn("prepare_scan_budget", yaml.safe_dump(workflow))
        self.assertNotIn("model_spend_reconciliation", yaml.safe_dump(workflow))

    def test_spend_snapshot_preserves_retained_ledger_and_exports_before_and_after(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = yaml.safe_load((root / ".github/workflows/scan.yml").read_text())
        steps = workflow["jobs"]["scan"]["steps"]
        snapshot = next(step for step in steps
                        if step.get("name") == "Snapshot retained model spend before scan")
        restore = next(step for step in steps if step.get("id") == "model-spend")
        scan = next(step for step in steps if step.get("run") == "job-agent scan-all")
        self.assertLess(steps.index(restore), steps.index(snapshot))
        self.assertLess(steps.index(snapshot), steps.index(scan))
        artifact = next(step for step in steps if step.get("uses") == "actions/upload-artifact@v4")
        self.assertIn("output/model_spend_before.json", artifact["with"]["path"].splitlines())
        self.assertIn("data/model_spend_ledger.json", artifact["with"]["path"].splitlines())
        for retained in (None, '{"2026-08": 9.12, "2026-09": 15.21}\n'):
            with self.subTest(retained=retained), tempfile.TemporaryDirectory() as directory:
                working = Path(directory)
                ledger = working / "data/model_spend_ledger.json"
                ledger.parent.mkdir()
                if retained is not None:
                    ledger.write_text(retained)
                    source_stat = ledger.stat()
                subprocess.run(["bash", "-eu", "-c", snapshot["run"]], cwd=working, check=True)
                before = working / "output/model_spend_before.json"
                self.assertTrue(before.is_file())
                if retained is None:
                    self.assertFalse(ledger.exists())
                    self.assertEqual(before.read_text().strip(), "{}")
                else:
                    self.assertEqual(ledger.read_text(), retained)
                    self.assertEqual(before.read_text(), retained)
                    self.assertEqual(ledger.stat().st_ino, source_stat.st_ino)
                    self.assertEqual(ledger.stat().st_mtime_ns, source_stat.st_mtime_ns)
