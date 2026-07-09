# Codex Build Brief — Stage 1.5 Web App ("Sextant")

**Goal:** ship the **4-page single-user web app** from the Sextant design as a read/act layer over the existing agent's real data + logic. Simple version of all 4 pages now (1.5); analytics/optimization/advanced tracker features are **2.0**.

**Design reference (recreate high-fidelity):** `docs/design/sextant/Sextant.dc.html` (dark = canonical) + `screenshots/` + `README.md`. The `.dc.html` has exact tokens, markup, and a JS logic class with state shape/handlers — read it. Light variant is optional, not v1.

**Gating: CLEARED (`f965590`, 2026-07-08).** The calibration stale-score fix is merged — stale pre-calibration evals are backfilled on scan (capped per run), old evaluator rows are version-filtered out of digest + calibration-floor reads, and the salary parser now reads only pay-adjacent spans. Regressions + benchmark gates + CI green. Build may start. Reuse that same current-version filter in the app so the UI only ever shows calibrated scores. **Sequencing:** build order step 1 (migration + skeleton + auth) does not display scores, so it can begin immediately; before step 2 (Potential Matches, which shows fit/band) confirm one live digest post-fix looks sane (no pre-calibration inflation).

---

## Non-negotiable: real logic & data, not the mock
The design's sample data is placeholder and **wrong on purpose-ignored details** — the build must use the real system, keeping ALL current rules:
- **Locations:** the owner is a **German citizen, EU-authorized**; US = high-friction/skip, not "US citizen." Use the real `location_policy.yaml` — never the mock's US roles or "US citizen & work authorization" text.
- **Fit-badge colours must key off the real recommendation bands** (`apply_now`/`consider`/`stretch` from the evaluator), i.e. **80+ / 70–79 / 60–69** — NOT the design README's standalone "85/65/45" buckets. Band drives colour.
- **All matching/evaluation stays in the Python agent.** The web app does **not** re-implement scoring, gating, or bands. It reads the agent's stored evaluations and provides the pipeline actions.
- Everything the UI shows (fit, band, evidence, chips, skip reasons, profile criteria) comes from the **real** `role_evaluations` / config, not hardcoded samples.

## Architecture
- **Stack:** Next.js + TypeScript + Tailwind · Supabase Postgres + Supabase Auth (single user — just the owner; deny anonymous) · Vercel. (Per `STAGE2_SCOPE.md`.)
- **Data:** migrate the agent's SQLite tables to Supabase Postgres (companies, job_sources, source_runs, job_postings, role_evaluations, opportunity_reviews) and point the Python scan at Postgres (or a sync step) so the web app and the agent share one store. Keep repo/ORM boundaries; one-way controlled migration, never overwrite the source data.
- The Python discovery+eval service stays as-is (scans, evaluates, emails). The web app is a **read + pipeline-action** layer on the same DB.
- **Only surface current-evaluator-version evals** (reuse the stale-version filter from the calibration fix) so the UI never shows pre-calibration scores. **⚠️ The version filter alone is NOT enough** (Cato, `f965590` review): it still admits deterministic fallback stubs (`DEFAULT_EVALUATOR_VERSION` / `is_fallback`), which the digest re-separates but a naive app read would render as if calibrated. **The app's data layer must additionally exclude fallback evals — show only `%|hybrid_claude_v2`, never `is_fallback` rows.** A role whose only evaluation is a fallback stub is treated as "not yet evaluated," not shown with a score.

## The 4 pages (all in 1.5)

### 1. Potential Matches (design first) — the daily digest, online
- Read the current-version surfaced evals grouped by band (Apply now / Consider / Stretch-collapsed). Role card: fit badge (band-coloured), company+title, chips (location · tier · feasibility% · confidence%), one-line summary, expand → top alignment ✓ + top gap △.
- **Role-detail slide-over** (the differentiator): full "Why it fits" = `alignments` rows (JD requirement → evidence + strength pip) and `gaps` (severity + mitigation) straight from `evaluation_json`.
- **Audit / "Skipped / all roles" toggle:** list every evaluated role incl. skip/blocked with the **real skip reason** (off-function / off-location / over-level / required-credential / language / below-fit-floor / duplicate / snoozed) — from the gate/penalty output.
- Actions: **Mark to apply** (→ page 2), Dismiss, Snooze, Open source. Quiet-day state uses the real calibration-floor "top 5 by fit."

### 2. To Apply — the shortlist
- Roles the owner marked interested (a new review state). Item: company · title · fit · location · note · age. Action: **Mark applied** (→ page 3, creates the application record). Remove / open role.

### 3. Applied — internal pipeline tracker
- Table: Company · Role · Location · **Stage** pill (`preparing → applied → recruiter screen → interviewing → final round → offer/rejected/withdrawn`) · Applied-on (+CW) · **Next action** · **Due** · Contact · Salary · Notes. Slim stat strip (active/in-interview/offers/closed) + compact funnel. NO streaks/vanity.
- Row → drawer: **immutable stage-change events** (actor/timestamp/prev→new) + the **original evaluation snapshot** (fit/alignments/gaps captured at mark-applied). Only "Mark applied" creates an application record.

### 4. Profile — READ-ONLY current criteria (visibility only)
- Display the **real, current** search parameters from config — NOT editable here (owner changes them via Codex/config; this page is for visibility). Pull live from `candidate_profile.yaml`, `location_policy.yaml`, `scoring_policy.yaml`, `watchlist.yaml`:
  - Target role families + approved-stretch families; seniority band (L4–L5, over-level rule); **real location allowlist** (W. Europe metros, Singapore, Australia; US high-friction) and work-auth (**German citizen / EU-authorized**, UK/SG sponsorship-routine); languages (German native, English fluent); hard blockers + disqualifiers; band thresholds (80/70/60); the company watchlist (32 companies, tiers) + last scan stats.
- Fix the design's placeholder text (it said "US citizen") — show the true values. Clearly framed "read-only — edit via config."

## Pipeline & rules
`Potential Matches → (Mark to apply) → To Apply → (Mark applied) → Applied`. Every transition is an explicit click; nothing auto-advances. Only "Mark applied" creates a tracked application (immutable events on every stage change). Human approval gates every consequential action (PRD §11.2, DECISIONS #5).

## State/schema additions
- Extend `opportunity_reviews.state` with `interested`; add `applications` (company, role, url, stage, applied_at + CW, next_action, due, contact, salary, notes, source_posting_id, eval_snapshot_json) + `application_events` (immutable). Migration report (imported/skipped/ambiguous).

## Build order (within 1.5)
1. Data migration SQLite→Postgres + Next.js/Supabase/Vercel skeleton + auth.
2. **Potential Matches + role-detail slide-over** (the daily surface, evidence view).
3. **Applied tracker** (table + stages + drawer + events).
4. **To Apply** + **Profile (read-only)**.
Each slice: build → Cato review → owner. Table view first for Applied (kanban is 2.0).

## Out of scope (→ 2.0)
Analytics/metrics dashboards, kanban, editable criteria in the UI, salary-anchoring, conversion analysis, multi-user, mobile-first, the light theme.
