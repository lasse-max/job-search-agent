"""Production count/ETA/spend only, in a server-enforced read-only transaction."""

from dataclasses import asdict
import json
import os

from app.postgres import PostgresConnection
from app.services.scheduled_scan import plan_stale_backfill_for_connection


def main() -> int:
    url = os.environ.get("JOB_AGENT_DATABASE_URL")
    if not url:
        print("Database connection is not configured; no preflight was run.")
        return 1
    conn = None
    try:
        conn = PostgresConnection(url, read_only=True)
        plan = plan_stale_backfill_for_connection(conn)
        print("transaction_read_only=on; no evaluations or database writes performed")
        print(json.dumps(asdict(plan), sort_keys=True))
        return 0
    except Exception as exc:
        print(f"Read-only backfill preflight failed: {type(exc).__name__}")
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
