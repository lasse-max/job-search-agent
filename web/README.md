# Sextant Web App

Stage 1.5 step 1 foundation only.

This app is a private Next.js + TypeScript + Tailwind shell over the job-search
agent's shared Supabase Postgres store. It does not score roles, assign bands,
or re-implement the evaluator. It only reads stored agent outputs through the
current calibrated-evaluator views.

## Required Environment

Set these in Vercel for the `web/` project:

```bash
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
OWNER_EMAIL=
```

Set this in the scanner runtime / GitHub Actions secrets when moving off the
SQLite cache:

```bash
JOB_AGENT_DATABASE_URL=
```

## Database Setup

Apply the migrations in order in Supabase:

1. `migrations/001_stage15_core.sql`
2. `migrations/002_stage15_supabase_auth.sql`

The first migration creates the agent tables and the read views:

- `current_calibrated_role_evaluations`
- `current_opportunity_evaluations`

Those views only expose latest evaluations whose `model_version` ends with the
current calibrated evaluator suffix, `|hybrid_claude_v2`, and whose provenance
is not marked as fallback.

The second migration enables RLS and grants read access only to authenticated
users whose email exists in `app_allowed_users`. Anonymous access has no table
grants.

## One-Way Import

Run the controlled import from the repo root:

```bash
job-agent migrate-postgres \
  --source data/job_search_agent.sqlite \
  --database-url "$JOB_AGENT_DATABASE_URL" \
  --owner-email "$OWNER_EMAIL" \
  --report output/sqlite_to_postgres_migration_report.md
```

The import never overwrites existing Postgres rows. Each row is reported as:

- `imported`: inserted into Postgres
- `skipped`: target already had the same row
- `ambiguous`: target had a conflict or a row-level import error

Ambiguous rows make the command exit non-zero so the migration cannot be missed.

## Local Web Commands

```bash
cd web
pnpm install
pnpm run dev
pnpm run typecheck
pnpm run build
```

## Scope Boundary

This slice stops at auth + data foundation. Potential Matches, To Apply,
Applied tracker, Profile, and all pipeline actions are intentionally locked
until Cato reviews this foundation.
