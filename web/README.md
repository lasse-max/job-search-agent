# Sextant Web App

Stage 1.5 A2 Potential Matches.

This app is a private Next.js + TypeScript + Tailwind shell over the job-search
agent's shared Supabase Postgres store. It does not score roles, assign bands,
or re-implement the evaluator. It only reads stored agent outputs through the
current calibrated-evaluator views.

## Vercel Setup

Create the Vercel project from this repository with `web/` as the project root.
`web/vercel.json` pins the deployment shape:

- Framework: Next.js
- Install command: `pnpm install --frozen-lockfile`
- Build command: `pnpm run build`
- Output directory: `.next`

## Required Vercel Environment

Set these in Vercel for the `web/` project:

```bash
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
OWNER_EMAIL=
```

`NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` are the normal
Supabase browser-safe project values. `OWNER_EMAIL` is server-side only and must
match the single allowed owner row seeded into `app_allowed_users`.

Do not set a Supabase service-role key in Vercel. The web app is read-only over
RLS-protected views and should only use the anon key.

Set this in the scanner runtime / GitHub Actions secrets, not in Vercel:

```bash
JOB_AGENT_DATABASE_URL=
```

## Supabase Auth Redirects

Before deploying, configure Supabase Auth URL settings for the Vercel domain:

- Site URL: `https://<vercel-domain>`
- Additional Redirect URL: `https://<vercel-domain>/auth/callback`
- Local development Redirect URL: `http://localhost:3000/auth/callback`

Without the `/auth/callback` redirect URL, passwordless or OAuth sign-in can
complete in Supabase but fail to establish the web session.

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

This slice renders Potential Matches and the role-detail slide-over from stored
agent evaluations only. To Apply, Applied tracker, Profile, and all pipeline
actions remain locked until Cato reviews this slice.
