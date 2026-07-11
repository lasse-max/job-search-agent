from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = REPO_ROOT / "migrations" / "003_stage15_applications.sql"


class AppliedTrackerSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = MIGRATION_PATH.read_text(encoding="utf-8")

    def test_tracker_schema_has_required_fields_and_stage_constraint(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS applications", self.schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS application_events", self.schema)
        for field in (
            "company TEXT NOT NULL",
            "role TEXT NOT NULL",
            "location TEXT NOT NULL",
            "applied_at TIMESTAMPTZ NOT NULL",
            "applied_calendar_week SMALLINT NOT NULL",
            "next_action TEXT",
            "due DATE",
            "contact TEXT",
            "salary TEXT",
            "notes TEXT",
            "source_posting_id INTEGER NOT NULL UNIQUE",
            "eval_snapshot_json JSONB NOT NULL",
        ):
            self.assertIn(field, self.schema)
        for stage in (
            "preparing",
            "applied",
            "recruiter_screen",
            "interviewing",
            "final_round",
            "offer",
            "rejected",
            "withdrawn",
        ):
            self.assertIn(f"'{stage}'", self.schema)

    def test_mark_applied_is_the_only_create_path_and_snapshots_current_calibration(self) -> None:
        function = self._function_body("public.mark_application_applied")

        self.assertIn("JOIN public.current_calibrated_role_evaluations evaluation", function)
        self.assertIn("jsonb_build_object(", function)
        self.assertIn("'role_evaluation_id', evaluation.id", function)
        self.assertIn("'model_version', evaluation.model_version", function)
        self.assertIn("'evaluation', evaluation.evaluation_json::jsonb", function)
        self.assertIn("'preparing'", function)
        self.assertIn("ON CONFLICT (source_posting_id) DO NOTHING", function)
        self.assertIn("owner access required", function)
        self.assertIn("posting has no current calibrated evaluation", function)
        self.assertIn("REVOKE ALL ON applications FROM anon, authenticated", self.schema)
        self.assertNotIn("GRANT INSERT ON applications TO authenticated", self.schema)

    def test_stage_history_and_snapshot_are_database_immutable(self) -> None:
        stage_trigger = re.search(
            r"CREATE TRIGGER application_stage_event\s+"
            r"AFTER INSERT OR UPDATE OF stage ON applications",
            self.schema,
        )
        immutable_event_trigger = re.search(
            r"CREATE TRIGGER application_events_immutable\s+"
            r"BEFORE UPDATE OR DELETE ON application_events",
            self.schema,
        )

        self.assertIsNotNone(stage_trigger)
        self.assertIn("OLD.stage IS NOT DISTINCT FROM NEW.stage", self.schema)
        self.assertIn("previous_stage", self.schema)
        self.assertIn("new_stage", self.schema)
        self.assertIn("(SELECT auth.jwt() ->> 'email')", self.schema)
        self.assertIsNotNone(immutable_event_trigger)
        self.assertIn("application events are immutable", self.schema)
        self.assertIn("application source and evaluation snapshot are immutable", self.schema)
        self.assertIn("BEFORE UPDATE ON applications", self.schema)
        for function_name in (
            "record_application_stage_event",
            "prevent_application_event_mutation",
            "protect_application_snapshot",
        ):
            self.assertIn(
                f"REVOKE EXECUTE ON FUNCTION private.{function_name}() FROM PUBLIC",
                self.schema,
            )

    def test_tracker_tables_keep_owner_only_rls_and_rpc_writes(self) -> None:
        for table in ("applications", "application_events"):
            self.assertIn(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY", self.schema)
            self.assertIn(f"GRANT SELECT ON {table} TO authenticated", self.schema)
            self.assertIn(f"REVOKE ALL ON {table} FROM anon, authenticated", self.schema)
        self.assertIn("CREATE POLICY owner_read_applications", self.schema)
        self.assertIn("CREATE POLICY owner_read_application_events", self.schema)
        self.assertEqual(
            self.schema.count(
                "WHERE lower(allowed.email) = lower((SELECT auth.jwt() ->> 'email'))"
            ),
            5,
        )
        self.assertEqual(self.schema.count("IF (SELECT auth.uid()) IS NULL"), 3)
        self.assertEqual(self.schema.count("SET search_path = ''"), 6)
        self.assertNotIn("TO anon USING", self.schema)
        self.assertNotRegex(
            self.schema,
            r"GRANT\s+(?:INSERT|UPDATE|DELETE).*?ON\s+applications\s+TO\s+authenticated",
        )
        self.assertIn(
            "GRANT EXECUTE ON FUNCTION public.mark_application_applied(INTEGER, TIMESTAMPTZ)",
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


class AppliedTrackerWebContractTest(unittest.TestCase):
    def test_web_read_path_preserves_historical_versions_and_rejects_fallbacks(self) -> None:
        source = (REPO_ROOT / "web" / "lib" / "data" / "applications.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("!modelVersion ||", source)
        self.assertNotIn(
            "!modelVersion.endsWith(`|${CURRENT_EVALUATOR_VERSION}`) ||",
            source,
        )
        self.assertIn(
            "isEarlierEvaluator: !modelVersion.endsWith(`|${CURRENT_EVALUATOR_VERSION}`)",
            source,
        )
        self.assertIn('modelVersion.toLowerCase().includes("deterministic_fallback")', source)
        self.assertIn("isFallbackEvaluation(evaluation)", source)
        self.assertIn("provenance?.is_fallback", source)
        self.assertIn("deterministic_fallback", source)

        drawer = (
            REPO_ROOT / "web" / "app" / "applied" / "applied-tracker-client.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("scored by {snapshot.modelVersion}", drawer)
        self.assertIn("earlier evaluator", drawer)

    def test_web_actions_use_narrow_rpcs_instead_of_table_writes(self) -> None:
        source = (REPO_ROOT / "web" / "app" / "applied" / "actions.ts").read_text(
            encoding="utf-8"
        )

        for function_name in (
            "mark_application_applied",
            "change_application_stage",
            "update_application_details",
        ):
            self.assertIn(f'"{function_name}"', source)
        self.assertNotRegex(source, r'\.from\(["\']applications["\']\)')
        self.assertIn("await requireOwner()", source)

    def test_table_is_working_tracker_without_vanity_or_kanban(self) -> None:
        source = (
            REPO_ROOT / "web" / "app" / "applied" / "applied-tracker-client.tsx"
        ).read_text(encoding="utf-8")

        for column in (
            "Company",
            "Role",
            "Location",
            "Stage",
            "Applied on",
            "Next action",
            "Due",
            "Contact",
            "Salary",
            "Notes",
        ):
            self.assertIn(f">{column}<", source)
        self.assertIn("Stage history", source)
        self.assertIn("Original evaluation", source)
        self.assertIn("active", source)
        self.assertIn("in interview", source)
        self.assertIn("offers", source)
        self.assertIn("closed", source)
        self.assertNotIn("streak", source.lower())
        self.assertNotIn("kanban", source.lower())


if __name__ == "__main__":
    unittest.main()
