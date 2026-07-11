from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
import unittest

from app.postgres import _translate_sql, postgres_core_schema
from app.services.postgres_migration import (
    AmbiguousRow,
    MigrationReport,
    TableMigrationResult,
    _connect_readonly_sqlite,
    _migrate_table,
    _redact_database_url,
)


class FakeCursor:
    rowcount = 1


class FakePostgresTarget:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> FakeCursor:
        self.statements.append((sql, params))
        return FakeCursor()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


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

    def test_postgres_translation_does_not_append_returning_to_bulk_upserts(self) -> None:
        translated = _translate_sql(
            """
            INSERT INTO job_postings (id, company_id, source_id, source_job_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title
            """
        )

        self.assertIn("ON CONFLICT (id) DO UPDATE SET", translated)
        self.assertNotIn("RETURNING id", translated)

    def test_sqlite_source_connection_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "source.sqlite"
            writer = sqlite3.connect(db_path)
            writer.execute("CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT)")
            writer.execute("INSERT INTO companies (id, name) VALUES (1, 'Example')")
            writer.commit()
            writer.close()

            source = _connect_readonly_sqlite(db_path)
            try:
                count = source.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
                self.assertEqual(count, 1)
                with self.assertRaises(sqlite3.OperationalError):
                    source.execute("INSERT INTO companies (id, name) VALUES (2, 'Nope')")
            finally:
                source.close()

    def test_migration_uses_batched_upserts_and_periodic_commits(self) -> None:
        source = sqlite3.connect(":memory:")
        source.row_factory = sqlite3.Row
        source.execute(
            """
            CREATE TABLE companies (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL,
              tier INTEGER NOT NULL,
              enabled INTEGER NOT NULL,
              warm_path INTEGER NOT NULL,
              notes TEXT
            )
            """
        )
        source.executemany(
            """
            INSERT INTO companies (id, name, tier, enabled, warm_path, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (1, "A", 1, 1, 0, None),
                (2, "B", 2, 1, 0, "note"),
                (3, "C", 3, 0, 1, None),
            ),
        )
        target = FakePostgresTarget()

        result = _migrate_table(source, target, "companies", batch_size=2)

        self.assertEqual(result.imported, 3)
        self.assertEqual(result.ambiguous, [])
        self.assertEqual(target.commits, 2)
        self.assertEqual(target.rollbacks, 0)
        self.assertEqual(len(target.statements), 2)
        self.assertIn("ON CONFLICT (id) DO UPDATE SET", target.statements[0][0])
        self.assertIn("VALUES (?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?)", target.statements[0][0])
        self.assertEqual(len(target.statements[0][1]), 12)
        self.assertEqual(len(target.statements[1][1]), 6)

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

    def test_migration_workflow_uses_replace_batches_and_escaped_like_pattern(self) -> None:
        workflow = Path(".github/workflows/migrate-postgres.yml").read_text(encoding="utf-8")

        self.assertIn("--batch-size 500", workflow)
        self.assertIn("--replace-target", workflow)
        self.assertIn("verify_only:", workflow)
        self.assertIn("if: ${{ !inputs.verify_only }}", workflow)
        self.assertIn("!inputs.verify_only && steps.import.outcome != 'success'", workflow)
        self.assertIn("policyname LIKE %s", workflow)
        self.assertIn('("owner_read_%",)', workflow)
        self.assertNotIn("policyname LIKE 'owner_read_%'", workflow)
        self.assertIn("ILIKE '%%deterministic_fallback%%'", workflow)
        self.assertNotIn("ILIKE '%deterministic_fallback%'", workflow)
        self.assertIn("verification script crashed", workflow)
        self.assertIn('report_path.write_text("\\n".join(lines) + "\\n"', workflow)


if __name__ == "__main__":
    unittest.main()
