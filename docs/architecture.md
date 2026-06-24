# Architecture

Single-user system, two logical halves: **Proactive** discovery/evaluation and a **Reactive** application tracker. Stage 1 ships the proactive half headless; Stage 2 adds the UI + database tracker.

## Processing flow (Stage 1)

1. Scheduler starts a run; load enabled sources + active config versions (profile, location, scoring).
2. Each source adapter fetches independently with timeout + bounded retry.
3. Normalize payloads; validate schemas; update source health + run metrics.
4. Deduplicate; update `first_seen_at` / `last_seen_at`.
5. Identify new or materially-changed roles.
6. Apply **true deterministic blockers** and feasibility policy (in code).
7. Evaluate eligible roles with the LLM → structured JSON (schema-validated).
8. Compute final fit + recommendation **in code**; persist an evaluation snapshot.
9. Generate the digest from unreviewed roles; send or save; record notification history.

A failed source never blocks the others, and a zero-job response is always distinguishable from a parser/auth failure.

## Components

- **Adapters** (`app/adapters/`) — one contract: `fetch / normalize / identity / health_check / fixtures`. Greenhouse, Lever, Ashby, plus `manual` intake.
- **Services** (`app/services/`) — `ingest, normalize, dedupe, health, evaluate, recommend, digest, notify`. Deterministic where possible.
- **Models** (`app/models.py`) — Pydantic canonical posting + evaluation schemas.
- **State** — SQLite via a repository/ORM layer that can later target Postgres without rewriting business logic.
- **Prompts/Templates** — versioned evaluation prompt; Jinja2 digest templates.

## Data model

Core tables: `profile_versions`, `location_policy_versions`, `companies`, `job_sources`, `source_runs`, `job_postings`, `role_evaluations`, `opportunity_reviews`, `notifications`. (Full field lists in [PRD §8](./PRD.md).) Every evaluation stores the profile/policy/prompt/model versions + input hash so decisions are reproducible and roles are never auto-rescored.

## Key properties

- **Idempotent** — replaying a run creates no duplicate postings, evaluations, reviews, or notifications.
- **Observable** — every run records status, counts, duration, errors, retries, last-known-good health.
- **Explainable** — every recommendation carries evidence, gaps, blockers, confidence, and version metadata.
- **Migration-ready** — SQLite now, Postgres at Stage 2, behind a repository boundary.

See [`DECISIONS.md`](../DECISIONS.md) for why each choice was made.
