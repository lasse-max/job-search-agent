"""Read-only production diagnostics; never emit role text or connection details."""

import json
import os

import psycopg


def main() -> int:
    database_url = os.environ.get("JOB_AGENT_DATABASE_URL")
    if not database_url:
        print("Database connection is not configured.")
        return 1
    try:
        with psycopg.connect(
            database_url,
            connect_timeout=20,
            prepare_threshold=None,
            options="-c default_transaction_read_only=on -c statement_timeout=20000",
        ) as conn:
            readonly = conn.execute("SHOW transaction_read_only").fetchone()[0]
            if readonly != "on":
                raise RuntimeError("read-only transaction required")
            print("transaction_read_only=on")
            for signature in (
                "public.remove_manual_intake(integer)",
                "public.replace_manual_intake_with_url(integer,text,text,text,text,text,text,boolean)",
            ):
                row = conn.execute(
                    """SELECT to_regprocedure(%s) IS NOT NULL,
                    has_function_privilege('authenticated', to_regprocedure(%s), 'EXECUTE'),
                    has_function_privilege('anon', to_regprocedure(%s), 'EXECUTE')""",
                    (signature, signature, signature),
                ).fetchone()
                print(json.dumps({"function": signature, "exists": row[0],
                                  "owner_role_can_execute": row[1], "anon_can_execute": row[2]}))
            rows = conn.execute(
                """SELECT status, count(*), max(length(jd_text)),
                count(*) FILTER (WHERE error_summary LIKE '%%400%%')
                FROM public.manual_intake_submissions GROUP BY status ORDER BY status"""
            ).fetchall()
            for status, count, max_text, rejected in rows:
                print(json.dumps({"status": status, "submissions": count,
                                  "max_jd_characters": max_text, "http_400_count": rejected}))
    except Exception as exc:
        # Exception messages can include the database host, user, or credentials.
        print(f"Read-only ingestion diagnostic failed: {type(exc).__name__}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
