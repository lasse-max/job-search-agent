# Codex Brief: PR #1 close-out, backfill runtime guard

Date: 2026-09-29. Author: Otto. Branch: `codex/retired-source-guards` (PR #1). **Effort: high.**
Push to the same PR branch. Do not merge. Pause for Cato.

## Why this exists

Cato reviewed PR #1 at `ebba8cb`, plus the uncommitted work that became `7e0def6`.
Since then you pushed `7e0def6` (MTD seed dropped), `54fad3c` (14-day window, newest first)
and `789befa` (preflight: 322 roles, $9.66, 1h47m scoring, about 3.5–4.5h end to end).
Cato has not reviewed those three commits yet, so there is one more review round no matter what.
Put the fixes below in that same round so the owner doesn't have to wait twice.

## Triage of Cato's PR #1 findings

| Finding | Call | Reason |
|---|---|---|
| 🟠 Full backfill: limit 10000, no `timeout-minutes`, commit once per company | **Accept, fix now** | The smaller run (322 roles, 3.5–4.5h) leaves about 1.5h under the 6h limit. That's not enough on this project: the v4 backfill estimate was wrong, and daily scans already spend about 2h on fetch/DB. If the job is killed, paid evaluations and the ledger save can be lost. The fix is small, and we'll need it again at the next version bump (B-33). |
| 🟡 `prepare_budget` could lower tracked spend | **Moot** | `7e0def6` deletes `prepare_budget` and the seed path. Cato to confirm nothing else can write a lower ledger value. |
| 🔵 Uncommitted local deletions of the budget plumbing | **Resolved** | That was `7e0def6` still in progress. It's committed and pushed now. |
| 🔵 Retirement report should show roles the owner has touched | **Accept** | Item 4 below. |
| Cato's "full backfill needs a reconciliation dated today" | **Superseded** | The owner dropped the MTD seed (ADR #105). With the item 1–3 guards, a 14-day, resumable backfill needs no console reconciliation. Cato to confirm no leftover gate. |

## Build

### 1. Wall-clock budget for backfill mode

- Add a config value in `config/recency_policy.yaml`, `backfill_wall_clock_budget_minutes: 270`, validated like the other recency values.
- Before each stale re-evaluation, check time elapsed since the scan started. Once it's over budget, **start no new evaluations**. Let the current one finish, commit, and let the rest of the scan (digest, run records) complete as usual.
- Log and report: `backfill stopped at wall-clock budget: N evaluated, M remaining`. Mark the run **degraded, not failed** (rule 8). Show it in the heartbeat or digest health line.
- It resumes because of how selection works: anything already evaluated is no longer stale, so the next dispatch or the daily trickle picks up the remaining M, newest first. **Show this in a test. Don't assume it.**
- Daily mode: apply the same budget. It should never fire at 25 per source, and if it ever does, we want to know.

### 2. Save work as it goes

- In the stale re-evaluation path, **commit after every evaluation**, or every N ≤ 10 if per-row commits measurably slow Postgres. Record the choice and the measurement in DECISIONS.md.
- Flush the spend ledger JSON at the same interval, so the `always()` save step always has current totals.

### 3. Workflow timeout

- `timeout-minutes: 330` on the scan job. Order: budget 270 < timeout 330 < GitHub hard limit 360. If the job runs away, we cancel it ourselves and the `always()` steps (ledger save, artifact upload) still have time to run.
- Add a unit test on the workflow, like `test_spend_workflow.py`, that fails if `timeout-minutes` is missing or ≥ 360, or if the budget in config isn't below it.

### 4. Retirement report: roles the owner has touched

- For each source, list postings whose review state isn't `new` (shortlisted, to-apply, applied, dismissed), with ID, company, title, state and last review date. Include these in the plan hash.
- The apply step already leaves review decisions and application history alone. The report just has to make that visible before the owner approves.

### 5. Owner-runnable retirement apply

The owner's way of touching production is Actions → Run workflow on `main`, not a local shell holding the production connection string.
- Add a `workflow_dispatch` path (in `diagnose-ingestion.yml` or its own workflow) with a required input `retirement_plan_hash`.
- It regenerates the report, compares hashes, and applies **only if they match exactly**. If they don't match, it refuses and prints the new hash, and nothing is written.
- It runs in the `scheduled-scan` concurrency group so it can never overlap a scan.

### 6. Tests that make the guards fire (rule 15)

- Fake clock: the budget runs out after k evaluations. Assert exactly k evaluations and k ledger entries are saved, the scan exits cleanly as degraded, M remaining is reported, and a second run evaluates the rest newest first with no duplicates.
- Simulate a crash partway through a company batch: the evaluations committed before the crash are still there.
- Retirement workflow: a mismatched hash refuses and makes no writes. A matching hash applies. Running it again changes zero rows.

### 7. Housekeeping (docs, straight to `main`, separate from the PR)

The owner's local checkout has uncommitted Otto doc edits on the PR branch: `docs/team-operating-brief.md`, `docs/BACKLOG.md`, `docs/briefs/*`, `data/evaluation_set/live_calibration_notes.md`. Move them to `main` as their own docs commit and don't mix them into PR #1. `docs/BACKLOG.md` also has duplicate rows for B-30 to B-33 (they appear twice). Keep one copy of each.

## Additions from Cato's second review (2026-09-29, verdict HOLD at `789befa`)

Cato reviewed the head before this brief was built. That review confirms items 1–5 (its P1 #1, P1 #2, P2 #4) and adds two defects. **All five findings are blocker-class for the backfill. Fix them in this round.**

### 8. Mid-company crash repro becomes a test (P1 #1)

Cato reproduced it: two paid evaluations, an exception, zero persisted, and both paid for again on retry (`app/services/ingest.py` around line 236). Turn that repro into the item 6 crash test, exactly as described. After item 2, the two evaluations must still be there after the crash, and the retry must not pay for them again.

### 9. Timestamp normalization (P2 #3)

`posted_at` / `first_seen_at` are compared **as strings** (`app/db.py` around line 912, `ORDER BY COALESCE(jp.posted_at, jp.first_seen_at) DESC` plus the cutoff comparison). With mixed UTC offsets, `12:00+00:00` sorts ahead of the genuinely newer `09:00-04:00` (13:00 UTC). A September 14 23:30-04:00 posting is wrongly excluded at a September 15 UTC cutoff.
- Normalize to UTC **once**, through one helper (rule 2), before filtering, ordering and limiting. Use the database's timestamp type or a normalized UTC column, whichever works in both SQLite and Postgres. Record the choice in DECISIONS.md.
- **Audit every recency comparison**, not just the backfill selector: the 21-day browse/digest filter, the web read layer, the `posted Nd ago` chip, and the daily trickle. Anything that compares these values as strings gets the same fix.
- Regression tests: mixed offsets under `LIMIT 1`, the exact cutoff boundary with a negative offset, and a missing `posted_at` falling back to first-seen.

### 10. Retirement replay must write nothing (P2 #5)

Replaying the same report closes zero postings, but it still updates the source row, so the database change count goes up by 1 (`app/services/source_retirement.py` around line 90). Make the source update conditional (only when state actually changes). The test must check **database changes are zero**, not just that the returned count is zero.

## Not in scope

Raising the cap, any MTD seed or console input, Deliveroo Greenhouse, new sources, evaluator or profile changes, moving the ledger into Postgres (logged as B-34).

## Deliverable

Push to PR #1. Update `docs/briefs/retired-source-launch-review.md` with the new guards. If selection changed, re-run the read-only preflight and report count, ETA and cost (it shouldn't change). Then stop and wait for Cato.
