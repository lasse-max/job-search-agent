# Stage 2 — Web App & Tracker · Scope

**Status:** proposed scope (Otto). **Gated:** requires owner approval AND Stage 1 actually delivering a reliable digest (precision ≥80%, email re-enabled). Expands the one-line ROADMAP entry; builds on PRD §11. **Do not start until the digest is trustworthy** — the tracker is only as good as what feeds it, and ROADMAP says the search comes first.

## What it is

Three web surfaces over the Stage 1 data, replacing CLI review and giving a durable home for the pipeline. The spreadsheet becomes export/backup only.

### The three pages (owner's model)

1. **New Opportunities** — the same ranked list the morning email sends. Read-only feed of newly evaluated roles (apply_now / consider / stretch), with source health. = PRD Opportunity Inbox (§11.2).
2. **Active Opportunities** — roles you've flagged "interested" from the digest/inbox. Your shortlist before you've applied. *(New state — see below.)*
3. **Application Tracker** — once you've applied: stages, dates, next action, contacts, notes, immutable history. = PRD Application Tracker (§11.3).

### The state model (one addition to the PRD)

PRD jumps Inbox → Approve → creates an application. Owner wants a middle **`interested`** state so roles can be shortlisted before committing to apply:

```
new (inbox)  →  interested (active opportunities)  →  applied (tracker: preparing → applied → screen → interviewing → offer/rejected/withdrawn)
                     ↓ dismiss                              ↑ immutable event on every transition
```

- From **email or website**, you mark a role `interested` → it appears on Active Opportunities.
- From Active Opportunities, "Applied" promotes it into the Tracker (creates exactly one application record).
- Only promotion-to-applied is consequential; everything stays human-approved (PRD §11.2: only Approve creates an application).

## Data model deltas (Stage 1 → Stage 2)

Stage 1 was built migration-ready (DECISIONS #3). Changes:
- Migrate SQLite → Supabase **Postgres** (companies, job_sources, source_runs, job_postings, role_evaluations, opportunity_reviews, notifications).
- Extend `opportunity_reviews.state` to include **`interested`** (already has new/approved/dismissed/snoozed).
- New **`applications`** table (company, role, url, current_stage, dates: found/approved/applied/last_activity, next_action, due_date, contact, doc_refs, notes).
- New **`application_events`** table — immutable (actor, source, timestamp, prev_value, new_value) on every stage change (PRD §11.3, NFR idempotency).
- Migration report: imported / skipped / ambiguous / duplicates (PRD §11.4). Never overwrite the source workbook.

## Select-from-email flow

Email digest cards get a one-click **"Mark interested"** link → a tokenized, single-purpose, expiring action endpoint on the web app that sets `interested` (no login required for that one action; signed token, not a session). Same action exists in-app. This is the only new security surface; keep it least-privilege (one role, one state change, signed + expiring).

## Stack (portfolio-consistent)

Next.js + TypeScript + Tailwind · Supabase Postgres + Supabase Auth · hosted on **Vercel** (matches Movie Match). The Stage 1 Python discovery service stays as-is (scans + evaluates + writes the DB); the web app reads/writes the shared Postgres. Single private repo for now (public when interview-ready, per portfolio policy).

## Sliced build plan (~8–10 focused build-days)

| # | Slice | Days |
|---|---|---:|
| 1 | Foundation: Next.js + Supabase Postgres + Auth + Vercel deploy | 1.5–2 |
| 2 | Migrate Stage 1 SQLite → Postgres + migration report | ~1 |
| 3 | New Opportunities page (read evals, source health) | 1.5 |
| 4 | Active Opportunities (`interested` state + mark/dismiss, from app) | ~1 |
| 5 | Application Tracker (stages, fields, immutable events) | ~2 |
| 6 | Select-from-email tokenized action links | 0.5–1 |
| 7 | Polish, auth hardening, tests, acceptance | ~1 |

Each slice: builder commits small → reviewer flags → Otto triages → owner decides. Table view first; **kanban and analytics deferred** (PRD §11.3).

## Acceptance (PRD §11.5 + the new state)

- Marking `interested` from email or web moves a role to Active Opportunities; no duplicate.
- Promoting to Applied creates exactly one `preparing` application; the evaluation snapshot used stays reproducible.
- Every stage change writes one immutable event.
- Active applications show stage, last activity, next action (or explicit none).
- Auth required; anonymous access denied (except the signed single-action email link).
- CSV/XLSX export reproduces the tracker.

## Non-goals (this stage)

Kanban, advanced analytics, Gmail integration (that's Stage 3), multi-user, auto-apply.

## Sequencing recommendation

Green-light **scoping** now; **build after ~1–2 weeks of a reliable digest** (precision cleared, email back on, real roles flowing). Until then the CLI review + CSV exports are a serviceable interim tracker. Watch the documented risk: *"portfolio work displaces real applications."* The app is satisfying to build — don't let it become procrastination from applying.
