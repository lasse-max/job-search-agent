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

The production login uses Supabase email + password auth, so normal sign-in
does not need an email round-trip or `/auth/callback`. Keep the callback route
configured for a future OAuth provider:

- Site URL: `https://<vercel-domain>`
- Optional OAuth Redirect URL: `https://<vercel-domain>/auth/callback`
- Optional local OAuth Redirect URL: `http://localhost:3000/auth/callback`

## Supabase Auth User Setup

This is a single-user app. Do not enable open sign-up.

In Supabase:

1. Enable the Email provider with password sign-in.
2. Create or update the owner in Authentication -> Users.
3. Set the owner's password in the dashboard.
4. Mark the owner email as confirmed / auto-confirmed so login returns a session directly.

The owner email must match both `OWNER_EMAIL` in Vercel and the allow-list row in
`app_allowed_users`. The RLS + allow-list gate remains the source of truth after
the password session is created.

Vercel auto-redeploys this app on merge / push to `main`.

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

The current web slice renders Potential Matches plus the Applied working
tracker. The tracker reads immutable evaluation snapshots created by the
database-backed `Mark applied` operation, records every stage change as an
immutable event, and exposes only narrow owner-authorized writes. To Apply and
Profile remain locked until their later reviewed slice.

Apply `migrations/003_stage15_applications.sql` to Supabase before opening
`/applied`. It adds the two tracker tables, owner-only RLS, calibrated
mark-applied/stage/detail RPCs, and the immutable event/snapshot triggers.
