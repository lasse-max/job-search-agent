# Codex Brief — Live Supabase Cutover (Stage 1.5 A1)

**Goal:** one-time SQLite→Postgres cutover so the agent (and the coming web app) share one always-on Supabase Postgres store. Runs **in CI**, not locally.

**Status when written (2026-07-08):** reviews cleared (`a2533db` foundation, `f965590` + `1cd4066` calibration). Supabase project live (region us-west-2/Oregon). Supabase MCP connected to Codex — DATABASE/DEBUGGING/DOCS, write-enabled (read-only OFF for the migration, flip back after). `JOB_AGENT_DATABASE_URL` (Session-pooler URI) set in **GitHub Actions secrets**. Owner is the only human who touches the connection string — never printed in chat, never committed.

## ⚠️ Data location (why this runs in CI)
The authoritative SQLite state lives in the **GitHub Actions cache** (`scan.yml` `actions/cache`, key `job-search-agent-db-*`), refreshed every daily run — **not** locally. The local `data/job_search_agent.sqlite` is a ~10-day-stale Jun-28 snapshot (31 companies / 7,058 postings / 1,340 evals). So the import must run **in CI**, where the fresh cache and the secret both exist. Do NOT run it locally against the stale copy. Note: `scan.yml` already wires `JOB_AGENT_DATABASE_URL` into `scan-all`, so the daily scan writes to Postgres going forward.

## Steps
1. **Schema.** Apply `migrations/001_stage15_core.sql` then `002_stage15_supabase_auth.sql` to Supabase (via the Supabase MCP DATABASE tools, or as the first step of the workflow below — your call). Confirm the six tables (companies, job_sources, source_runs, job_postings, role_evaluations, opportunity_reviews) + the single-user RLS/auth guard exist.
2. **One-off import workflow.** Add a manual `workflow_dispatch` job — e.g. `.github/workflows/migrate-postgres.yml` — that:
   - restores the SQLite cache (same `key`/`restore-keys` as `scan.yml`),
   - installs the project,
   - runs `job-agent migrate-postgres --owner-email "$OWNER_EMAIL"` with `JOB_AGENT_DATABASE_URL: ${{ secrets.JOB_AGENT_DATABASE_URL }}` and `OWNER_EMAIL` supplied from an existing GitHub secret,
   - uploads `output/sqlite_to_postgres_migration_report.md` as an artifact.
   One-way only — never mutate the SQLite source. Push it so the owner can trigger it from the Actions tab.
3. **Verify** (via MCP DATABASE/DEBUGGING): per-table Postgres row counts match the source (expect roughly companies 31, job_postings ~7,058, role_evaluations ~1,340 — likely a bit higher from fresher cache); the calibrated read view returns **only `%|hybrid_claude_v2`**, excluding `is_fallback` and stale `|hybrid_claude_v1` (the 🟡C requirement from the `f965590` review); no errors.
4. **Report back** the migration-report summary + verification counts. Never print the connection string/password; never commit `.env`.

## Sequence / owner action
Codex applies schema + pushes the one-off `migrate-postgres` workflow → **owner clicks "Run workflow"** in the Actions tab → Codex + Otto check the migration report and row counts. Owner does not touch the DB file or run anything locally.

## After verify
Flip the Supabase MCP to **read-only** (or disconnect) — no standing write access to the DB once the cutover is done — then proceed to **A2 (Potential Matches)** per `docs/briefs/webapp-build-brief.md`.
