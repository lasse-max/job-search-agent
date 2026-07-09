# Project Status — job-search-agent

Living status doc. Single source of truth for *where things stand right now and who's holding what*. Complements `DECISIONS.md` (why), `ROADMAP.md` (direction), and `docs/briefs/` (what to build). Update at each checkpoint. **Owner of this doc:** George (coordinator).

**Last updated:** 2026-07-08 · **Branch:** `main`

## 🟢 STAGE 1.5 — web-app gate CLEARED; build unblocked (2026-07-08)

**Calibration stale-score fix shipped (`f965590`, Cato 🟠 closed).** Stale pre-calibration evaluations are now backfilled on each scan (capped per run, under the monthly spend cap), and old evaluator-version rows are filtered out of both the digest and the calibration-floor reads — so the DB no longer surfaces pre-calibration inflation (the native-PMs-at-87 class). Salary parsing now reads only pay-adjacent spans, so `$180,000 salary, requisition 9999999` no longer falsely down-ranks. Regressions added (stale-version re-eval, digest version filter, salary/requisition). `ruff` green · 125 tests green · benchmark recall/precision gates green · CI green (`28988776521`). Follow-ups parked as **B-21** (backfill admin/visibility) + **B-22** (richer comp parsing); **DECISIONS #65** logged.

**This unblocks the Stage 1.5 web app** (`docs/briefs/webapp-build-brief.md`). Sequencing: build-order step 1 (SQLite→Postgres migration + Next.js/Supabase/Vercel skeleton + auth) can start now (it displays no scores); before step 2 (Potential Matches, which renders fit/band) confirm one live post-fix digest looks sane. App must reuse the current-version filter so the UI only ever shows calibrated scores.

**`f965590` reviewed → SHIP (Cato, no 🔴/🟠).** Three 🟡 follow-ups: (a) fallback-discard test + (b) UK "per annum"/"annually"/`p.a.`/comma-context salary parsing → **both shipped in `1cd4066`** (calibration-only, 131 tests green, CI `28991140872`) — awaiting Cato review; (c) **the app data layer must exclude fallback evals — show only `%|hybrid_claude_v2`, never `is_fallback`** — the version filter alone admits deterministic stubs [baked into the web-app brief; verify in the app read layer].

**`a2533db` "Add Stage 1.5 web foundation" landed on `main` (2026-07-08).** Codex built + committed the A1 foundation (Postgres migrations `001_stage15_core` + `002_stage15_supabase_auth`, `test_postgres_foundation`, Next.js/Tailwind/Supabase-Auth skeleton in `web/`, DECISIONS #66) ahead of the formal go — clean self-contained commit, CI green (`28990664258`), but **not yet reviewed**. Codex did **not** run the migration against live Supabase (no `JOB_AGENT_DATABASE_URL` locally). Next handoff: **Cato reviews `a2533db` against the Stage-1.5 checklist** (reviewing code/schema, not a live cutover). Then continue to A2 (Potential Matches).

**⏳ LIVE SUPABASE CUTOVER — in progress (reviews cleared 2026-07-08).** Supabase project live (region us-west-2/Oregon; owner in SF). `JOB_AGENT_DATABASE_URL` (Session-pooler URI) set in GitHub Actions secrets. Supabase MCP connected to Codex (DATABASE/DEBUGGING/DOCS, write-enabled, read-only OFF for the migration — flip back after). **Key finding:** the authoritative SQLite state lives in the **GitHub Actions cache** (`scan.yml actions/cache`), not locally — local copy is a Jun-28 snapshot (31 companies / 7,058 postings / 1,340 evals, ~10 days stale). So the one-time import runs **in CI** (fresh cache + secret both present), NOT locally against stale data. `scan.yml` already wires `JOB_AGENT_DATABASE_URL` into `scan-all`, so the daily scan writes to Postgres going forward.

**Cutover workflow pushed — `ff5efcb` "Add Supabase cutover workflow" (CI green, run `28993221576`).** `.github/workflows/migrate-postgres.yml`: restores the SQLite Actions cache, runs `job-agent migrate-postgres` in CI only, applies the RLS/auth migration after import, uploads `output/sqlite_to_postgres_migration_report.md` + `output/postgres_verification.md` (checks row-count parity, RLS/policies, allowed-owner row, calibrated-view safety). Owner email comes from the `DIGEST_RECIPIENT_EMAIL` secret (no real email committed). Codex also patched `current_calibrated_role_evaluations` to **exclude fallback provenance**, not just old evaluator versions (closes 🟡C at the view level). Brief: `docs/briefs/supabase-cutover-brief.md`.

**▶ OWNER NEXT ACTION:** in GitHub Actions, run **"One-off SQLite to Postgres Migration"** manually, then send Codex the run id/status → Codex pulls the reports + verifies counts. After verify: flip the Supabase MCP to read-only, run one live digest (A1.5 check), then A2 (Potential Matches).

---

## 🟢 STAGE 1.5 — live agent + search refinement; 1.5 opportunity-list in design (2026-06-29)

Roadmap split (owner): **1.0 shipped** (daily email agent) → **1.5** = search refinement + user testing + an online **opportunity list** (hot leads to apply, with a Skipped/all-roles audit view + running list) → **2.0** = applied tracker.

- **Calibration loop shipped (`a729689`) → in Cato review.** From the 2026-06-29 digest review: **strict monotonic bands** (DECISIONS #61: fit-only, 80+/70–79/60–69/<60; removed the Tier-1+warm-path upward override that inverted ranking — warm-path/tier now feed the fit *score*); function gate now skips head-function false-positives (Recruiter, SRE, Solutions Architect, Technical PM) regardless of "GTM/Operations" keywords; required-credential gaps down-rank fit; multi-location dedup. **No brand-specific logic** (owner: stop treating Databricks differently). 112 tests; gated metrics hold (curated recall 100%/precision 90%; live apply/consider precision 100%/recall 90%; all-surfaced 47.4% report-only — expected stretch-inclusion effect). Calibration notes: `live_calibration_notes.md`.
- **1.5 design:** `docs/design/stage2_design_brief.md` updated — Opportunity Inbox + role detail + **Skipped/all-roles audit view** + running list = design first; Application Tracker deferred to 2.0.
- **Cadence:** once daily `0 6 * * *` (confirmed unchanged). Extra emails owner saw = manual Run-workflow triggers.

---

## 🟢 LIVE, TUNED & OPERATING (2026-06-27)

Stage 1 is live, delivering, and now tuned to the owner's preference. All review loops closed (Cato SHIP on `558a6c5`). The agent: scans the watchlist **once daily (`0 6 * * *`)** → calibrated Claude eval → capped **Layline-dark** email that is **never empty** (always ≥5: "Top open roles by fit — may repeat" floor on quiet days) and carries **no false source alarms**.

**Shipped this cycle (all Cato-cleared):**
- **Email redesign** (`2bfead0` + `03bbae5`) — Layline dark brand, email-hardened, behavior preserved. PII scrubbed from the design mockups (synthetic data).
- **Daily cadence + always-≥5 calibration floor + Atlassian disable** (`6e94684` → `558a6c5`) — floor draws top-by-fit from the open pool (dedup-overridden, scoped to the floor only — real bands still dedup, no daily Harvey re-send); disabled sources no longer flag (`enabled=1` filter); label band-agnostic; all mutation-proven.

**Open owner loose ends (tiny):**
- **Commit `.gitignore`** — Otto added `*.xlsx` (blocks the real interim tracker from ever being committed; currently an uncommitted local edit). `git add .gitignore && commit`.
- **Decide the `candidate_profile.yaml` "Senior Associate" edit** — fixed + valid; commit + push to make it live (loosens the level filter; watch digests).
- Glance `ruff` green (Cato couldn't run lint locally).

**Calibration & next:**
- Calibration notes logged (`live_calibration_notes.md`): 2 Databricks false-positives (Tier-1 brand inflating sales/pre-sales to apply_now) → feeds B-15.
- **Stage 2 (2.0) in design** — `docs/design/stage2_design_brief.md` (Layline, 3 screens) for Claude design; `docs/STAGE2_SCOPE.md` = engineering scope.
- **Reminder:** apply to the live roles (Harvey first). Quiet-day digests repeat until roles are triaged (`job-agent review dismiss/approve`) — Stage 2 makes that one-click.

---

## 🟢 LIVE + FIX-FREEZE — launch-day history (2026-06-25 → 27)

**SHIPPED 2026-06-25.** Stage 1 is live: all 3 secrets set (`ANTHROPIC_API_KEY`, `RESEND_API_KEY`, `DIGEST_RECIPIENT_EMAIL`), `scan.yml` wires them (`fa94381`), evaluator calibrated + Cato-cleared (`915149f`). Scheduled scan + digest every 6h; manual run via Actions → Scheduled Scan → Run workflow. Then **freeze fixes for a couple of days and operate** — apply to jobs, learn Python. "The search comes first." During the freeze the live digest runs and the owner flags real-world good/noise roles → that becomes the next calibration input.

First-run results (2026-06-25): scan healthy — 31 sources, ~8k postings, gated to 15–24 new roles (not a firehose ✅). Two shakeout issues:
- **(resolved)** `ANTHROPIC_API_KEY` secret — first run fell back because the key wasn't reaching the job; now set correctly, Claude runs live.
- **(fixed `2887d7b`, ✅ Cato SHIP)** live Claude returned `alignments` as a JSON string → validation crashed → email blocked. Fix: coerce JSON-string list fields before validation; retry-once-then-drop the single bad role (logged, source degraded); digest still sends valid roles; all-fail still blocks loud. Cato mutation-verified both directions; firehose protection confirmed working empirically. 99 tests.
- **🟠 follow-up DONE (`55e76d7`, in Cato confirm):** `FailAllRolesProvider` regression test now locks the all-fail firehose-protection guard (all roles fail → scan failure, 0 persisted, source failing, no role cards). 100 tests. Once Cato confirms non-vacuous, the **code side is fully closed** — every flagged item across all six review loops resolved.
- **✅ Cato SHIP on `81015f4` (Fix Loop 6).** Cap genuinely enforced both modes (mutation-proven + empirical 40→25 + DEGRADED label + overflow). Normal withholds/counts fallback rows; all-fallback sends capped labeled degraded digest (never zero, never >25). Transient 429/529 retry bounded. 103 tests, no secrets printed.
- **🟡 non-blocking follow-up (parallel):** make `render_html`/`render_text` self-enforce the 25 cap (caller-convention only today — how 93 leaked once; it's the sole firehose guardrail) + render-level test. Does not gate live email.
- **✅ FULLY LIVE — first real digest delivered (2026-06-27).** RESEND_API_KEY set; email landed. First apply_now: **Harvey — GTM Strategy & Operations, EMEA (London), fit 87 / conf 88** — on-target family, right level (Senior IC), allowed location, viable feasibility, with real JD→evidence mapping and honest gaps (the calibrated evaluator working as designed, not boilerplate). Discovery → gate → calibrated LLM eval → capped digest → email is working end to end. Stage 1 complete and operating.
- **Optional follow-ups (parallel, non-blocking):** B-17 calibration floor (quiet days), B-18 render-cap hardening, B-15 stretch-band tuning, B-16 diagnostics. Owner now in fix-freeze / operate mode (apply to jobs, learn Python).
- Owner unblocked meanwhile: applying from the 16-role interim tracker. Atlassian feed still degraded (fetched 0) — harmless, backlog.

- **Ship action (owner):** on Cato SHIP for `915149f`, re-add `RESEND_API_KEY` + `DIGEST_RECIPIENT_EMAIL` repo secrets → digest live. Only a 🔴 from Cato pauses the ship; 🟡/🔵 are parked.
- **Parked until resume (do NOT action during freeze):** widen positive label set (10 candidates ready) · stretch-band tuning B-15 + Palantir-defense down-rank · `role_family_fit=82` floor follow-up · Stage 2 web app (scoped, gated) · hosted CI green confirmation.
- **Other projects:** Movie Match also paused for testing (~couple days). Portfolio overview = George's `Layline_Project_Tracker.html`.

---

## Headline

Stage 1 / MVP shipped — but the **first live digest (June 24) was a 1,064-role firehose** of off-target roles (Payroll, Legal, Sales, Engineering) recommended "apply now." Root cause: live email was wired onto the **uncalibrated deterministic stub evaluator**, which had only ever been measured on 33 hand-curated roles (100% recall / 90% precision) — so the benchmark never tested rejecting a real feed's ~97% noise. We are now mid-fix on the real evaluator. **Live email is paused until precision clears.**

## Done (recent)

- Live email paused (Resend secrets removed → local-file fallback only).
- Guardrails shipped (`a36ae0c`): loud fallback, corrected cost-cap math, gate-leak fixes.
- Relevance gate now filters on **location** (owner allowlist), **function families**, an **L4–L5 seniority ceiling**, plus **hard-credential** and **defense** blockers — owner strategy now encoded, not tribal.
- Two 150-role benchmark sets labeled (Otto, from owner judgment): gate-recall set + gate-passer **precision** set (1 apply / 9 consider / 2 stretch / 138 skip).

## Done (this cycle, `0f81524`)

- Labeled benchmark sets + seniority ceiling #52 committed; `benchmark` now uses cached LLM outputs by default with `--populate-llm-cache` for the one-time Claude run. 83 tests green.

## In flight — Fix Loop 4 (single remaining email-blocker) 🔧

- Evaluator calibrated across loops: firehose → too-stingy → **calibrated** (`34ebc3c`/`7a6cb44`): apply/consider precision 9/9, recall 9/10, LNP-090→apply_now, LNP-020→consider; stretch precision reported separately (11/20, report-only, DECISIONS #56, residual noise → B-15). Cato confirmed genuine mechanism fix, not overfit (mutation-tested).
- **Cato cleared (SHIP):** 🟠-A stretch-metric mismatch (`7a6cb44`) and the calibration mechanism (`34ebc3c`).
- **✅ Cato SHIP on `915149f` — technical gate CLEARED.** 🟠-B genuinely closed: synthetic production-coding case now `blocked`, new regression tests non-vacuous by mutation (incl. nice-to-have negative), no over-correction (all consider roles + LNP-090 apply_now preserved), `role_family_fit=82` floor sound/not-masking (DECISIONS #57), loud-fallback + cost carry-overs tested. 97 tests, ruff clean (local; hosted CI still to confirm on the Actions tab).
- **Email NOT live yet — on-switch only half-flipped.** Owner set `RESEND_API_KEY` + `DIGEST_RECIPIENT_EMAIL` secrets ✅, but (a) `.github/workflows/scan.yml`'s scheduled-scan step has **no `env:` block**, so secrets never reach the run, and (b) the run also needs `ANTHROPIC_API_KEY` as a repo secret (else loud-fallback correctly refuses to email). **Two remaining ship steps:** owner adds `ANTHROPIC_API_KEY` secret; Codex adds the `env:` block to scan.yml (wiring ANTHROPIC_API_KEY/MODEL, RESEND_API_KEY, DIGEST_RECIPIENT_EMAIL, MONTHLY_MODEL_SPEND_CAP_USD). This is ship wiring, not a calibration fix — allowed during freeze. Then live (monitored soft-launch); ongoing Claude cost capped at $15/mo.
- Thin positive set: owner accepted as-is (will realistically apply to ~3 roles; precision matters more than positive-recall). 🟡 redundant preferred-assertion test → backlog.
- **Owner decision: monitored soft-launch.** After 🟠-B fixed + Cato clears + owner sign-off → re-enable email (re-add `RESEND_API_KEY` + `DIGEST_RECIPIENT_EMAIL`). Owner monitors stretch cards; label-set widening runs in parallel. (Cato flags the thin positive set — ~10 — as doubly relevant now stretch is visible-but-untuned; owner accepted this tradeoff for soft-launch.)
- Recurring: hosted GitHub Actions CI unverified from build env — owner to check the Actions tab.

## Not-until

- **Live email** re-enables only after live precision ≥80% with the real evaluator **and** owner sign-off.
- Hosted GitHub Actions CI status unverified from build env — check the Actions tab on each push.

## Open decisions for owner

None pending — all current calls triaged (location #50, hard-requirement #51, seniority #52, defense-skip on Palantir).

## Team & flow

Lasse = owner (decides) · Otto = product/strategy (plans, triage, briefs) · Codex = builder · Cato = independent reviewer · George = coordinator.
Flow: Codex builds a slice → Cato reviews independently (🔴/🟠/🟡/🔵 + verdict) → Otto triages vs. roadmap → owner decides → Codex actions next.
