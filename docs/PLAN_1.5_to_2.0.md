# Plan — Stage 1.5 → 2.0 (sequenced)

Living plan map for the path from the current state to 2.0. Complements `ROADMAP.md` (direction), `STATUS.md` (where things stand), `DECISIONS.md` (why), and `docs/briefs/webapp-build-brief.md` (what to build). **Owner:** Otto (product) · **Status doc:** George · **Build:** Codex · **Review:** Cato · **Approve:** owner.

Four phases: **build the app → live-test & calibrate → close out 1.5 → optimize (2.0)**. Nothing in a later phase starts until the phase before it has earned it. Every build slice is the same loop: **Codex builds → Cato reviews → owner approves → merge.** One slice open at a time.

**Where we are now:** start of **A1**, with **A1.5** running alongside. Web-app gate cleared by `f965590` (calibration stale-score fix).

---

## Phase A — Build the 4-page app (core of 1.5)

Per `docs/briefs/webapp-build-brief.md`, in four slices.

### A1. Foundation — migration + skeleton + auth
- Migrate the six SQLite tables (companies, job_sources, source_runs, job_postings, role_evaluations, opportunity_reviews) into Supabase Postgres as a one-way controlled sync; emit an imported/skipped/ambiguous migration report; never overwrite source data.
- Point the Python scan at Postgres.
- Stand up Next.js + TypeScript + Tailwind + Supabase Auth on Vercel — single user, deny anonymous.
- Reuse the current-evaluator-version filter (from `f965590`) in the data layer so the app can only ever read calibrated evals.
- **No scores rendered yet** — this is plumbing.
- **Gate:** migration report clean · agent still scans/writes to Postgres · owner can log in, nobody else can.

### A1.5. Live-digest verification *(parallel; must clear before A2)*
- Owner triggers one scan (or waits for the 6am run) and forwards the digest.
- Otto confirms calibration holds in the wild — no pre-calibration inflation (the native-PMs-at-87 class is gone).
- Real-world proof behind `f965590` that the tests can't give. Only after this looks sane do we render fit/band on screen.

### A2. Potential Matches + role-detail slide-over *(the differentiator — most value lives here)*
- Digest online: roles grouped by band; fit badge colored off the real **80/70/60** bands; chips (location · tier · feasibility% · confidence%); expand → top alignment + top gap.
- Slide-over: full alignments (JD requirement → evidence + strength) and gaps (severity + mitigation) from `evaluation_json`.
- Skipped/all-roles audit toggle with real skip reasons (off-function / off-location / over-level / required-credential / language / below-fit-floor / duplicate / snoozed).
- Actions: Mark to apply · Dismiss · Snooze · Open source. Quiet-day = real calibration-floor top-5-by-fit.
- **Gate:** every number on screen traces to a real `role_evaluations` row.

### A3. Applied tracker — internal pipeline
- Table: Company · Role · Location · Stage pill · Applied-on (+CW) · Next action · Due · Contact · Salary · Notes. Slim stat strip + compact funnel. Table view only (kanban = 2.0).
- Row-drawer: immutable stage-change events (actor/timestamp/prev→new) + evaluation snapshot captured at mark-applied.
- **Gate:** "Mark applied" is the only thing that creates an application record; every stage change writes an immutable event.

### A4. To Apply + Profile (read-only)
- To Apply: the shortlist (new `interested` review state); Mark applied → creates the application record.
- Profile: read-only display of the **real** current criteria from config — location allowlist (**German citizen, EU-authorized**, not the mock's "US citizen"), L4–L5 band + over-level rule, function families + approved-stretch, blockers/disqualifiers, languages (German native / English fluent), 80/70/60 thresholds, the 32-company watchlist. Framed "read-only — edit via config."
- **Gate:** Profile shows true values, zero mock placeholders.

**End of Phase A:** all four pages working end-to-end on real data.

---

## Phase B — Live-test & refine (the other half of 1.5)

The app existing isn't the goal — the owner *running the search through it daily* is.

- **B1. Daily operation.** Triage Potential Matches each morning → mark to apply → apply → track in Applied. The interim `.xlsx` tracker retires once this is trustworthy.
- **B2. Calibration feedback loop.** Every disagreement (wrong band, good role wrongly skipped, off skip reason) → `live_calibration_notes.md`. Otto triages · Codex tunes gates/thresholds · Cato reviews. No brand-specific logic; strict monotonic bands hold (DECISIONS #61).
- **B3. UX friction pass.** Log real annoyances; the genuine ones get fixed in 1.5, "nice to have" ones become the 2.0 backlog.
- **B4. B-15 stretch-band tuning** finishes here — defense/gov skips, pre-sales, language filter, validated against live stretch cards now visible in the audit view.

---

## Phase C — Close out 1.5

1.5 is done when all three hold:
1. All four pages work on real data, Cato-cleared slice by slice.
2. Owner runs the search through the app daily without fighting it or falling back to the spreadsheet.
3. Calibration is trustworthy enough to act on bands without second-guessing.

Then George stamps STATUS, we freeze. **The search comes first** — the app is a tool for applying, not a thing to keep polishing.

---

## Phase D — 2.0 = optimize the app

Only after 1.5 is stable and *used* — live usage tells us which of these actually matter. Rough priority (finalized after Phase B):
- **Analytics/metrics** — funnel conversion, response rates, time-in-stage.
- **Kanban** view for Applied (table was deliberately first).
- **Editable criteria in the UI** — change search parameters in Profile instead of via Codex/config (the big one).
- **Salary-anchoring / conversion analysis by CV version** — the deeper analytical layer.
- **Light theme.**

Which of these leads 2.0 is decided *after* Phase B, informed by what the owner actually reached for.
