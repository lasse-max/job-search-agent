from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "migrations" / "004_stage15_shortlist.sql"


class ShortlistSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = MIGRATION.read_text(encoding="utf-8")

    def test_shortlist_writes_are_owner_gated_current_calibration_rpcs(self) -> None:
        for function_name in (
            "public.mark_opportunity_interested",
            "public.remove_opportunity_interest",
        ):
            body = self._function_body(function_name)
            self.assertIn("IF (SELECT auth.uid()) IS NULL", body)
            self.assertIn("public.app_allowed_users", body)
            self.assertIn("owner access required", body)
            self.assertIn("SET search_path = ''", body)

        mark_body = self._function_body("public.mark_opportunity_interested")
        self.assertIn("public.current_opportunity_evaluations", mark_body)
        self.assertIn("evaluation.availability_state = 'open'", mark_body)
        self.assertIn("'interested'", mark_body)
        self.assertIn("length(cleaned_note) > 1000", mark_body)
        self.assertIn("FROM PUBLIC, anon", self.schema)
        self.assertIn("TO authenticated", self.schema)
        self.assertNotRegex(
            self.schema,
            r"GRANT\s+(?:INSERT|UPDATE|DELETE).*opportunity_reviews.*authenticated",
        )

    def test_mark_applied_closes_interest_with_a_database_trigger(self) -> None:
        self.assertIn("CREATE TRIGGER application_closes_shortlist", self.schema)
        self.assertIn("AFTER INSERT ON public.applications", self.schema)
        trigger_body = self._function_body("private.close_shortlist_on_application")
        self.assertIn("IF (SELECT auth.uid()) IS NULL", trigger_body)
        self.assertIn("public.app_allowed_users", trigger_body)
        self.assertIn("state = 'approved'", trigger_body)
        self.assertIn("AND state = 'interested'", trigger_body)
        self.assertIn("NEW.source_posting_id", trigger_body)
        self.assertIn(
            "REVOKE EXECUTE ON FUNCTION private.close_shortlist_on_application() FROM PUBLIC",
            self.schema,
        )

    def _function_body(self, function_name: str) -> str:
        match = re.search(
            rf"CREATE OR REPLACE FUNCTION {re.escape(function_name)}\(.*?\n\$\$;",
            self.schema,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match, f"missing function {function_name}")
        return match.group(0) if match else ""


class ShortlistWebContractTest(unittest.TestCase):
    def test_live_shortlist_keeps_current_version_and_fallback_guards(self) -> None:
        source = (REPO_ROOT / "web" / "lib" / "data" / "shortlist.ts").read_text(
            encoding="utf-8"
        )
        evaluator = (
            REPO_ROOT / "web" / "lib" / "data" / "calibrated-evaluations.ts"
        ).read_text(encoding="utf-8")

        self.assertIn('.from("current_opportunity_evaluations")', source)
        self.assertIn('.eq("review_state", "interested")', source)
        self.assertIn('.like("model_version", CURRENT_EVALUATOR_VERSION_SUFFIX)', source)
        self.assertIn("normalizeCurrentEvaluation(row)", source)
        self.assertIn("isFallbackEvaluation(evaluation)", evaluator)

    def test_actions_use_rpc_only_and_pipeline_is_click_driven(self) -> None:
        actions = (
            REPO_ROOT / "web" / "app" / "actions" / "opportunities.ts"
        ).read_text(encoding="utf-8")
        matches = (REPO_ROOT / "web" / "app" / "potential-matches-client.tsx").read_text(
            encoding="utf-8"
        )
        shortlist = (
            REPO_ROOT / "web" / "app" / "to-apply" / "to-apply-client.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn('"mark_opportunity_interested"', actions)
        self.assertIn('"remove_opportunity_interest"', actions)
        self.assertIn("await requireOwner()", actions)
        self.assertNotIn('.from("opportunity_reviews")', actions)
        self.assertIn("<MarkToApplyButton jobPostingId={role.id}", matches)
        self.assertIn("markApplied(role.id)", shortlist)
        self.assertIn("removeFromShortlist(role.id)", shortlist)
        self.assertIn("Nothing shortlisted — mark roles from Potential Matches.", shortlist)
        self.assertIn("Open source", shortlist)


if __name__ == "__main__":
    unittest.main()
