from __future__ import annotations

from pathlib import Path
import unittest

from app.postgres import _translate_sql, postgres_core_schema
from app.services.postgres_migration import (
    AmbiguousRow,
    MigrationReport,
    TableMigrationResult,
    _redact_database_url,
)


class PostgresFoundationTest(unittest.TestCase):
    def test_postgres_translation_preserves_insert_ignore_semantics(self) -> None:
        translated = _translate_sql(
            """
            INSERT OR IGNORE INTO role_evaluations (
              job_posting_id, input_hash, model_version
            )
            VALUES (?, ?, ?)
            """
        )

        self.assertIn("INSERT INTO role_evaluations", translated)
        self.assertIn(
            "ON CONFLICT (job_posting_id, input_hash, model_version) DO NOTHING",
            translated,
        )
        self.assertEqual(translated.count("%s"), 3)

    def test_postgres_translation_returns_inserted_job_ids(self) -> None:
        translated = _translate_sql(
            """
            INSERT INTO job_postings (company_id, source_id, source_job_id)
            VALUES (?, ?, ?)
            """
        )

        self.assertTrue(translated.endswith("RETURNING id"))

    def test_core_schema_exposes_only_current_calibrated_evaluations(self) -> None:
        schema = postgres_core_schema()

        self.assertIn("current_calibrated_role_evaluations", schema)
        self.assertIn("latest.model_version LIKE '%|hybrid\\_claude\\_v2' ESCAPE '\\'", schema)
        self.assertIn("latest.model_version NOT ILIKE '%deterministic_fallback%'", schema)
        self.assertIn("{provenance,fallback_quality}", schema)
        self.assertIn("{provenance,is_fallback}", schema)
        self.assertNotIn("deterministic_fallback_v1", schema)

    def test_migration_report_redacts_target_and_surfaces_ambiguous_rows(self) -> None:
        report = MigrationReport(
            source_path=Path("data/job_search_agent.sqlite"),
            target=_redact_database_url("postgresql://user:secret@example.supabase.co/postgres"),
            owner_seeded=True,
            tables=(
                TableMigrationResult(
                    table="companies",
                    imported=1,
                    skipped=2,
                    ambiguous=[AmbiguousRow("companies", 42, "target differs")],
                ),
            ),
        )

        markdown = report.to_markdown()

        self.assertIn("postgresql://***@example.supabase.co/postgres", markdown)
        self.assertIn("imported `1`, skipped `2`, ambiguous `1`", markdown)
        self.assertIn("`companies` id `42`: target differs", markdown)
        self.assertNotIn("secret", markdown)


if __name__ == "__main__":
    unittest.main()
