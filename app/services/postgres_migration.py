"""Controlled SQLite -> Postgres import for Stage 1.5."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlsplit

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
    target_replaced: bool = False

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
            f"- Target import tables replaced before import: `{str(self.target_replaced).lower()}`",
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
    batch_size: int = 500,
    replace_target: bool = False,
) -> MigrationReport:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    source = _connect_readonly_sqlite(source_path)
    target: PostgresConnection | None = None
    try:
        target = connect_postgres(database_url)
        init_db(target)
        if replace_target:
            _replace_import_tables(target)
        owner_seeded = _seed_owner(target, owner_email)
        results = []
        for table in (*MIGRATION_TABLES, *AUXILIARY_TABLES):
            results.append(_migrate_table(source, target, table, batch_size=batch_size))
        _reset_sequences(target)
        target.commit()
        report = MigrationReport(
            source_path=source_path,
            target=_redact_database_url(database_url),
            owner_seeded=owner_seeded,
            tables=tuple(results),
            target_replaced=replace_target,
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report.to_markdown(), encoding="utf-8")
        return report
    finally:
        source.close()
        if target is not None:
            target.close()


def _connect_readonly_sqlite(source_path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(source_path.resolve()))}?mode=ro"
    source = sqlite3.connect(uri, uri=True)
    source.row_factory = sqlite3.Row
    source.execute("PRAGMA query_only = ON")
    return source


def _replace_import_tables(target: PostgresConnection) -> None:
    tables = ", ".join((*MIGRATION_TABLES, *AUXILIARY_TABLES, "app_allowed_users"))
    target.execute(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE")
    target.commit()


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
    *,
    batch_size: int = 500,
) -> TableMigrationResult:
    result = TableMigrationResult(table=table)
    columns = _source_columns(source, table)
    if not columns:
        return result
    column_list = ", ".join(columns)
    source_cursor = source.execute(f"SELECT {column_list} FROM {table} ORDER BY id")
    while rows := source_cursor.fetchmany(batch_size):
        try:
            cursor = target.execute(
                _bulk_upsert_sql(table, columns, row_count=len(rows)),
                _flatten_rows(rows, columns),
            )
            target.commit()
        except Exception as exc:  # noqa: BLE001 - migration must report row-level failures.
            target.rollback()
            _migrate_rows_individually(rows, columns, target, result, exc)
            continue
        result.imported += len(rows) if cursor.rowcount >= 0 else len(rows)
    return result


def _migrate_rows_individually(
    rows: list[sqlite3.Row],
    columns: list[str],
    target: PostgresConnection,
    result: TableMigrationResult,
    batch_error: Exception,
) -> None:
    sql = _bulk_upsert_sql(result.table, columns, row_count=1)
    for row in rows:
        try:
            target.execute(sql, tuple(row[column] for column in columns))
            target.commit()
        except Exception as exc:  # noqa: BLE001 - keep migrating independent rows.
            target.rollback()
            result.ambiguous.append(
                AmbiguousRow(
                    table=result.table,
                    row_id=int(row["id"]),
                    reason=(
                        f"batch {type(batch_error).__name__}: {batch_error}; "
                        f"row {type(exc).__name__}: {exc}"
                    ),
                )
            )
            continue
        result.imported += 1


def _bulk_upsert_sql(table: str, columns: list[str], *, row_count: int) -> str:
    column_list = ", ".join(columns)
    row_placeholders = "(" + ", ".join("?" for _ in columns) + ")"
    values = ", ".join(row_placeholders for _ in range(row_count))
    update_columns = [column for column in columns if column != "id"]
    if update_columns:
        conflict_action = "DO UPDATE SET " + ", ".join(
            f"{column} = EXCLUDED.{column}" for column in update_columns
        )
    else:
        conflict_action = "DO NOTHING"
    return (
        f"INSERT INTO {table} ({column_list}) VALUES {values} "
        f"ON CONFLICT (id) {conflict_action}"
    )


def _flatten_rows(rows: list[sqlite3.Row], columns: list[str]) -> tuple[object, ...]:
    return tuple(row[column] for row in rows for column in columns)


def _source_columns(source: sqlite3.Connection, table: str) -> list[str]:
    rows = source.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row["name"]) for row in rows]


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


_DATABASE_URL_RE = re.compile(r"\bpostgres(?:ql)?://[^\s'\"`]+", re.IGNORECASE)
_CONNECTION_FIELD_RE = re.compile(
    r"\b(host|hostaddr|user|password|dbname|database)\s*=\s*"
    r"(?:'[^']*'|\"[^\"]*\"|[^\s,;]+)",
    re.IGNORECASE,
)
_QUOTED_CONNECTION_FIELD_RE = re.compile(
    r"\b(host|user|dbname|database)\s+(?:'[^']*'|\"[^\"]*\")",
    re.IGNORECASE,
)
_RESOLVED_SERVER_ADDRESS_RE = re.compile(
    r"\((?:(?:\d{1,3}\.){3}\d{1,3}|[0-9a-f:]{2,})\)(?=,\s*port\b)",
    re.IGNORECASE,
)


def redact_database_error(error: BaseException, database_url: str) -> str:
    """Remove connection identifiers before an error reaches logs or artifacts."""

    message = str(error)
    parsed = urlsplit(database_url)
    sensitive_values = {
        database_url,
        parsed.netloc,
        parsed.hostname,
        parsed.password,
    }
    for value in sorted((value for value in sensitive_values if value), key=len, reverse=True):
        message = message.replace(value, "[redacted]")

    if parsed.username:
        message = re.sub(
            rf"(?<![\w]){re.escape(parsed.username)}(?![\w])",
            "[redacted]",
            message,
        )
    message = _DATABASE_URL_RE.sub("postgresql://[redacted]", message)
    message = _CONNECTION_FIELD_RE.sub(
        lambda match: f"{match.group(1)}=[redacted]",
        message,
    )
    message = _QUOTED_CONNECTION_FIELD_RE.sub(
        lambda match: f"{match.group(1)} [redacted]",
        message,
    )
    return _RESOLVED_SERVER_ADDRESS_RE.sub("([redacted])", message)
