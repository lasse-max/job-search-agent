"""Controlled SQLite -> Postgres import for Stage 1.5."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from app.db import init_db
from app.postgres import PostgresConnection, connect_postgres


MIGRATION_TABLES = (
    "companies",
    "job_sources",
    "source_runs",
    "job_postings",
    "role_evaluations",
    "opportunity_reviews",
)
AUXILIARY_TABLES = (
    "evaluation_skips",
    "notifications",
)


@dataclass(frozen=True)
class AmbiguousRow:
    table: str
    row_id: int
    reason: str


@dataclass
class TableMigrationResult:
    table: str
    imported: int = 0
    skipped: int = 0
    ambiguous: list[AmbiguousRow] = field(default_factory=list)


@dataclass(frozen=True)
class MigrationReport:
    source_path: Path
    target: str
    owner_seeded: bool
    tables: tuple[TableMigrationResult, ...]

    @property
    def imported(self) -> int:
        return sum(table.imported for table in self.tables)

    @property
    def skipped(self) -> int:
        return sum(table.skipped for table in self.tables)

    @property
    def ambiguous(self) -> int:
        return sum(len(table.ambiguous) for table in self.tables)

    def to_markdown(self) -> str:
        lines = [
            "# SQLite to Postgres Migration Report",
            "",
            f"- Source: `{self.source_path}`",
            f"- Target: `{self.target}`",
            f"- Owner allow-list seeded: `{str(self.owner_seeded).lower()}`",
            f"- Totals: imported `{self.imported}`, skipped `{self.skipped}`, "
            f"ambiguous `{self.ambiguous}`",
            "",
            "| Table | Imported | Skipped | Ambiguous |",
            "| --- | ---: | ---: | ---: |",
        ]
        for result in self.tables:
            lines.append(
                f"| `{result.table}` | {result.imported} | {result.skipped} | "
                f"{len(result.ambiguous)} |"
            )
        ambiguous_rows = [
            ambiguous
            for table in self.tables
            for ambiguous in table.ambiguous
        ]
        if ambiguous_rows:
            lines.extend(["", "## Ambiguous Rows", ""])
            for row in ambiguous_rows:
                lines.append(f"- `{row.table}` id `{row.row_id}`: {row.reason}")
        return "\n".join(lines) + "\n"


def migrate_sqlite_to_postgres(
    *,
    source_path: Path,
    database_url: str,
    report_path: Path,
    owner_email: str | None = None,
) -> MigrationReport:
    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    target = connect_postgres(database_url)
    init_db(target)
    owner_seeded = _seed_owner(target, owner_email)
    results = []
    for table in (*MIGRATION_TABLES, *AUXILIARY_TABLES):
        results.append(_migrate_table(source, target, table))
    _reset_sequences(target)
    target.commit()
    report = MigrationReport(
        source_path=source_path,
        target=_redact_database_url(database_url),
        owner_seeded=owner_seeded,
        tables=tuple(results),
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.to_markdown(), encoding="utf-8")
    return report


def _seed_owner(target: PostgresConnection, owner_email: str | None) -> bool:
    if not owner_email:
        return False
    target.execute(
        """
        INSERT INTO app_allowed_users (email)
        VALUES (?)
        ON CONFLICT (email) DO NOTHING
        """,
        (owner_email.lower(),),
    )
    target.commit()
    return True


def _migrate_table(
    source: sqlite3.Connection,
    target: PostgresConnection,
    table: str,
) -> TableMigrationResult:
    result = TableMigrationResult(table=table)
    columns = _source_columns(source, table)
    if not columns:
        return result
    placeholders = ", ".join("?" for _ in columns)
    column_list = ", ".join(columns)
    rows = source.execute(f"SELECT {column_list} FROM {table} ORDER BY id").fetchall()
    for row in rows:
        row_id = int(row["id"])
        existing = target.execute(
            f"SELECT {column_list} FROM {table} WHERE id = ?",
            (row_id,),
        ).fetchone()
        if existing is not None:
            if _rows_equal(columns, row, existing):
                result.skipped += 1
            else:
                result.ambiguous.append(
                    AmbiguousRow(
                        table=table,
                        row_id=row_id,
                        reason="target id already exists with different values",
                    )
                )
            continue
        try:
            cursor = target.execute(
                f"""
                INSERT INTO {table} ({column_list})
                VALUES ({placeholders})
                ON CONFLICT (id) DO NOTHING
                """,
                tuple(row[column] for column in columns),
            )
            target.commit()
        except Exception as exc:  # noqa: BLE001 - migration must report row-level failures.
            target.rollback()
            result.ambiguous.append(
                AmbiguousRow(table=table, row_id=row_id, reason=f"{type(exc).__name__}: {exc}")
            )
            continue
        if cursor.rowcount > 0:
            result.imported += 1
        else:
            result.ambiguous.append(
                AmbiguousRow(table=table, row_id=row_id, reason="conflict on non-id constraint")
            )
    return result


def _source_columns(source: sqlite3.Connection, table: str) -> list[str]:
    rows = source.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row["name"]) for row in rows]


def _rows_equal(columns: list[str], source_row: sqlite3.Row, target_row: dict[str, object]) -> bool:
    return all(_normalize(source_row[column]) == _normalize(target_row[column]) for column in columns)


def _normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _reset_sequences(target: PostgresConnection) -> None:
    for table in (*MIGRATION_TABLES, *AUXILIARY_TABLES):
        target.execute(
            """
            SELECT setval(
              pg_get_serial_sequence(?, 'id'),
              COALESCE((SELECT MAX(id) FROM %s), 1),
              (SELECT MAX(id) FROM %s) IS NOT NULL
            )
            """
            % (table, table),
            (table,),
        )


def _redact_database_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    host = parsed.hostname or "postgres"
    database = parsed.path.lstrip("/") or "database"
    return f"{parsed.scheme}://***@{host}/{database}"
