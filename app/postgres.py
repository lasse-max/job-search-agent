"""Postgres connection compatibility layer for the Stage 1.5 shared store.

The Stage 1 agent was built on SQLite's DB-API. Step 1 of the web app keeps
that business logic intact and swaps only the connection underneath when a
Postgres URL is provided.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


CORE_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "migrations" / "001_stage15_core.sql"


class CompatRow(dict[str, Any]):
    """Mapping row that also supports SQLite-style positional indexing."""

    def __init__(self, columns: list[str], values: tuple[Any, ...]) -> None:
        super().__init__(zip(columns, values, strict=True))
        self._columns = columns

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return super().__getitem__(self._columns[key])
        return super().__getitem__(key)


class PostgresCursor:
    def __init__(
        self,
        rows: list[CompatRow],
        *,
        rowcount: int,
        lastrowid: int | None = None,
    ) -> None:
        self._rows = rows
        self._index = 0
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def fetchone(self) -> CompatRow | None:
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self) -> list[CompatRow]:
        rows = self._rows[self._index :]
        self._index = len(self._rows)
        return rows


class PostgresConnection:
    dialect = "postgres"

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ModuleNotFoundError as exc:  # pragma: no cover - exercised only without dependency.
            raise RuntimeError(
                "Postgres support requires psycopg. Install with `pip install -e .`."
            ) from exc

        self.database_url = database_url
        self._conn = psycopg.connect(
            database_url,
            connect_timeout=20,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
            prepare_threshold=None,
        )

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> PostgresCursor:
        translated_sql = _translate_sql(sql)
        with self._conn.cursor() as cursor:
            cursor.execute(translated_sql, tuple(params))
            columns = [column.name for column in cursor.description] if cursor.description else []
            values = cursor.fetchall() if cursor.description else []
            rows = [CompatRow(columns, tuple(row)) for row in values]
            lastrowid = int(rows[0]["id"]) if rows and "id" in rows[0] else None
            return PostgresCursor(rows, rowcount=cursor.rowcount, lastrowid=lastrowid)

    def executescript(self, sql: str) -> None:
        with self._conn.cursor() as cursor:
            for statement in _split_sql_script(sql):
                cursor.execute(statement)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def connect_postgres(database_url: str) -> PostgresConnection:
    return PostgresConnection(database_url)


def is_postgres_connection(conn: object) -> bool:
    return getattr(conn, "dialect", None) == "postgres"


def postgres_core_schema() -> str:
    return CORE_SCHEMA_PATH.read_text(encoding="utf-8")


def _translate_sql(sql: str) -> str:
    translated = sql.strip()
    translated = translated.replace(
        "SET expected_volume_min = MAX(COALESCE(expected_volume_min, 0), ?)",
        "SET expected_volume_min = GREATEST(COALESCE(expected_volume_min, 0), ?)",
    )
    translated = translated.replace(
        "INSERT OR IGNORE INTO opportunity_reviews",
        "INSERT INTO opportunity_reviews",
    )
    translated = translated.replace(
        "INSERT OR IGNORE INTO role_evaluations",
        "INSERT INTO role_evaluations",
    )
    translated = translated.replace(
        "INSERT OR IGNORE INTO evaluation_skips",
        "INSERT INTO evaluation_skips",
    )
    if (
        translated.startswith("INSERT INTO opportunity_reviews")
        and "ON CONFLICT" not in translated
    ):
        translated += " ON CONFLICT (job_posting_id) DO NOTHING"
    if translated.startswith("INSERT INTO role_evaluations") and "ON CONFLICT" not in translated:
        translated += " ON CONFLICT (job_posting_id, input_hash, model_version) DO NOTHING"
    if translated.startswith("INSERT INTO evaluation_skips") and "ON CONFLICT" not in translated:
        translated += " ON CONFLICT (job_posting_id, input_hash, reason) DO NOTHING"
    if (
        translated.startswith("INSERT INTO job_postings")
        and "RETURNING" not in translated
        and "ON CONFLICT" not in translated
    ):
        translated += " RETURNING id"
    if (
        translated.startswith("INSERT INTO notifications")
        and "RETURNING" not in translated
        and "ON CONFLICT" not in translated
    ):
        translated += " RETURNING id"
    return translated.replace("?", "%s")


def _split_sql_script(sql: str) -> list[str]:
    return [statement.strip() for statement in sql.split(";") if statement.strip()]
