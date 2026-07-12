from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "migrations" / "008_stage15_manual_intake.sql"


class ManualIntakeWebTest(unittest.TestCase):
    def test_migration_is_owner_gated_and_scanner_owned(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS manual_intake_submissions", sql)
        self.assertIn("CREATE OR REPLACE FUNCTION public.submit_manual_intake", sql)
        self.assertIn("owner access required", sql)
        self.assertIn("ALTER TABLE manual_intake_submissions FORCE ROW LEVEL SECURITY", sql)
        self.assertIn("REVOKE ALL ON TABLE manual_intake_submissions", sql)
        self.assertIn("GRANT SELECT ON TABLE manual_intake_submissions TO authenticated", sql)
        self.assertIn("CHECK (intake_mode IN ('url', 'text', 'manual'))", sql)
        self.assertNotIn("service_role", sql.lower())

    def test_add_role_ui_exposes_the_three_fallbacks_and_destinations(self) -> None:
        client = (REPO_ROOT / "web" / "app" / "add-role" / "add-role-client.tsx").read_text(
            encoding="utf-8"
        )
        action = (REPO_ROOT / "web" / "app" / "add-role" / "actions.ts").read_text(
            encoding="utf-8"
        )
        processor = (REPO_ROOT / "app" / "services" / "manual_intake.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('key: "url"', client)
        self.assertIn('key: "text"', client)
        self.assertIn('key: "manual"', client)
        self.assertIn("no PDF upload", client)
        self.assertIn('value="potential_matches"', client)
        self.assertIn('value="to_apply"', client)
        self.assertIn('value="applied"', client)
        self.assertIn("Propose this company for the watchlist", client)
        self.assertIn('rpc("submit_manual_intake"', action)
        self.assertIn("process_manual_intake_queue", processor)
        self.assertIn("add_text_intake(", processor)

    def test_manual_unscored_entries_are_visible_but_not_in_calibrated_views(self) -> None:
        cards = (REPO_ROOT / "web" / "app" / "manual-intake-cards.tsx").read_text(
            encoding="utf-8"
        )
        loader = (REPO_ROOT / "web" / "lib" / "data" / "manual-intake.ts").read_text(
            encoding="utf-8"
        )
        calibrated = (
            REPO_ROOT / "web" / "lib" / "data" / "calibrated-evaluations.ts"
        ).read_text(encoding="utf-8")
        self.assertIn('"not evaluated"', cards)
        self.assertIn('"manual_unscored"', loader)
        self.assertIn('loadOpenManualIntakes(supabase, "potential_matches")', calibrated)
        self.assertNotIn("manual_unscored", calibrated)


if __name__ == "__main__":
    unittest.main()
