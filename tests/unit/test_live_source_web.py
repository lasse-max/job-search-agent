from pathlib import Path
import re
import unittest

from app.services.evaluate import HYBRID_EVALUATOR_VERSION


ROOT = Path(__file__).resolve().parents[2]


class LiveSourceWebTest(unittest.TestCase):
    def test_scan_bootstrap_and_owner_migration_keep_identical_guarded_view(self):
        def view_query(path):
            source = (ROOT / path).read_text()
            match = re.search(
                r"CREATE (?:OR REPLACE )?VIEW current_calibrated_role_evaluations"
                r"\s+WITH \(security_invoker = true\) AS\s+(.*?);",
                source,
                re.DOTALL,
            )
            self.assertIsNotNone(match, f"missing guarded view in {path}")
            return " ".join(match.group(1).split())

        bootstrap = view_query("migrations/001_stage15_core.sql")
        migration = view_query("migrations/010_stage15_active_source_reads.sql")
        self.assertEqual(bootstrap, migration)
        for guard in (
            "js.company_id = c.id",
            "lower(js.health_status) NOT IN ('disabled', 'retired')",
            "(js.source_type = 'manual' OR c.enabled = 1)",
        ):
            self.assertIn(guard, bootstrap)

    def test_owner_applied_view_keeps_calibration_and_rls_without_touching_history(self):
        source = (ROOT / "migrations/010_stage15_active_source_reads.sql").read_text()
        self.assertIn("WITH (security_invoker = true)", source)
        self.assertIn("SELECT re.*", source)
        self.assertIn("lower(js.health_status) NOT IN ('disabled', 'retired')", source)
        self.assertIn("(js.source_type = 'manual' OR c.enabled = 1)", source)
        expected = HYBRID_EVALUATOR_VERSION.replace("_", r"\_")
        self.assertIn(f"LIKE '%|{expected}'", source)
        for fallback in ("is_fallback", "fallback_quality", "deterministic_fallback"):
            self.assertIn(fallback, source)
        self.assertIn("FROM PUBLIC, anon", source)
        self.assertNotRegex(source, r"(?i)\b(?:DELETE|TRUNCATE|UPDATE|INSERT)\s")

    def test_password_hint_adds_no_signup_reset_or_secret(self):
        source = (ROOT / "web/app/login/login-form.tsx").read_text()
        self.assertIn('aria-describedby="password-hint"', source)
        self.assertIn("Supabase Dashboard: Authentication &gt; Users", source)
        self.assertIn("not your email password", source)
        self.assertIn("signInWithPassword", source)
        self.assertNotIn("resetPasswordForEmail", source)
        self.assertNotIn("signUp(", source)


if __name__ == "__main__":
    unittest.main()
