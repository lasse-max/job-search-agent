# Codex Brief: post-PR #1 follow-ups

Date: 2026-09-29. Author: Otto. **Start only after PR #1 is merged** and the owner confirms migration 010 and the merge are done. Effort: **medium**. Docs go straight to `main`; any code goes in a PR.

## 1. Close Cato's 🟠: deploy runbook (docs only, direct to `main`)

Cato's `fbbe27d` review found that every scan runs `init_db`, and `init_db` re-runs `001`. So an old-`main` scan between applying 010 and the merge silently reverts 010, and the new web then fails with `column effective_at does not exist`. Update **ADR 108** and `docs/briefs/retired-source-launch-review.md` with the sequence the owner actually follows:

1. Confirm no Scheduled Scan is running or queued. Scheduled runs actually start **10:00–12:30 UTC** (GitHub delays the 06:00 cron) and take about 2–2.5h.
2. Apply the migration from the PR branch, then merge immediately.
3. Verify with `SELECT effective_at FROM current_opportunity_evaluations LIMIT 1;`. If it fails, re-apply the migration (it's idempotent).

Make this the **standing rule for any future migration that the web reads**: migration immediately before merge, with nothing running between them. Add one line to rule 11 in the team operating brief.

## 2. Backlog rows to add (`docs/BACKLOG.md`, direct to `main`)

| ID | Item | Why deferred | Revisit |
|---|---|---|---|
| B-35 | **In-app password recovery.** The owner has been locked out twice. Supabase's reset link has no destination in the app (no recovery handler or set-password page), so it lands on /login. Add a `/auth/callback` recovery branch that opens a set-password page (`updateUser({ password })`), reachable only with a valid recovery session. Keep the owner-email and allow-list gates unchanged. | This is an auth change, so it needs a PR and Cato review. The SQL Editor workaround takes about 2 minutes, and a password manager covers most cases. | Next small PR. Bundle with B-26 if that starts first. |
| B-36 | **Scan runtime monitoring (Cato 🔵, `fbbe27d`).** Daily scans grew from about 1h (Sep 17–20) to 2h07m–2h42m (Sep 24–28). The 270-min budget stops scoring, not fetching. Log time per source (fetch, DB, evaluation). Put a warning in the heartbeat or digest when a daily scan goes past about 3h. Find out what doubled the runtime. | PR #1's guards protect paid work and the ledger even on a hard kill. A failed run with no digest is the remaining risk, and the missing heartbeat already makes that visible. | Before the next coverage batch. More sources means more fetch time. |
| B-37 | **Runtime schema DDL (Cato 🔵, pre-existing).** Every scan re-runs `001` (DROP and CREATE of the views) on production. Owner-applied migrations can silently revert, and 010's explicit `REVOKE … FROM anon` only lasts until the next scan (Supabase default grants come back). RLS should still return zero rows to anon. The owner verifies that after the merge with `SET ROLE anon`. Either stop running DDL at runtime (schema version check only), or keep enforcing `001` and later migrations in lockstep with a test, as PR #1 does. | PR #1's cross-check covers the current views. Fixing this properly is a design change. | Next migration batch, or right away if the anon check ever returns rows. |
| B-38 | **The preflight doesn't count the resume set (Cato 🔵).** Roles within 21 days that changed or were interrupted before scoring are paid work with no per-source cap, and the backfill preflight doesn't count them. Add them to the preflight's count, ETA and cost. | The 270-min budget caps runtime, so a miscount now means leftover roles for the next day, not a killed run. It was zero on the June copy. | Next change to the preflight script. |

## 3. Report

Give the commit hash for the docs. No code, no production writes, no workflow dispatches.
