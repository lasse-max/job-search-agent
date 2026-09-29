"""Apply an exact owner-approved hash after regenerating a read-only report.

A successful apply changes the plan. Re-running Actions with the old hash is
therefore a read-only refusal, not permission to retire any newly arrived roles.
The owner must review the fresh report and approve its hash for a new dispatch.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.config import DEFAULT_DB_PATH, OUTPUT_DIR
from app.services.source_retirement import (
    RetirementPlanMismatch,
    apply_retirement_report,
    connect_for_retirement,
    write_retirement_report,
)


def run_retirement(approved_hash: str, *, db_path: Path = DEFAULT_DB_PATH,
                   report_path: Path = OUTPUT_DIR / "source_retirement.json") -> int:
    conn = None
    try:
        conn = connect_for_retirement(db_path)
        report = write_retirement_report(conn, report_path)
        conn.close()
        conn = None
        print(f"retirement_plan_hash={report['plan_hash']} postings={report['posting_count']}")
        if approved_hash != report["plan_hash"]:
            print("Retirement refused: hash mismatch; database_writes=0. "
                  "Review the new report before approving its hash.")
            return 1
        conn = connect_for_retirement(db_path, apply=True)
        closed = apply_retirement_report(conn, report, expected_plan_hash=approved_hash)
        print(f"retirement_applied={closed} plan_hash={approved_hash}")
        return 0
    except RetirementPlanMismatch as exc:
        report_path.write_text(json.dumps(exc.current_report, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        print(f"retirement_plan_hash={exc.current_report['plan_hash']}")
        print("Retirement refused: plan changed before apply; database_writes=0. "
              "Review the new report before approving its hash.")
        return 1
    except Exception as exc:
        print(f"Source retirement failed: {type(exc).__name__}; no connection details logged")
        return 1
    finally:
        if conn is not None:
            conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retirement-plan-hash", required=True)
    args = parser.parse_args(argv)
    if not os.environ.get("JOB_AGENT_DATABASE_URL"):
        print("Database connection is not configured; no retirement was run.")
        return 1
    return run_retirement(args.retirement_plan_hash)


if __name__ == "__main__":
    raise SystemExit(main())
