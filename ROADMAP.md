# Roadmap

Staged delivery. Each stage stands alone and delivers value before the next begins. Build only the current approved stage; pause at each checkpoint for owner review. Estimates are focused build-days for an owner using a coding agent — multiply for calendar time.

## Stage 0 — Source audit & setup · _complete_
**Goal:** know exactly what we can cover before writing adapters.
- Repository + config schemas (done in scaffold)
- Read the master tracker; build a source-coverage matrix for every target company
- Select the first 10–15 Tier 1/2 companies on Greenhouse/Lever/Ashby
- Confirm the labelled evaluation set (≥20–30 roles) — see [`data/evaluation_set/`](./data/evaluation_set/evaluation_set.yaml)

**Exit (Checkpoint A):** every company has a documented source status (`Supported` / `Needs configuration` / `Manual fallback` / `Unsupported`); ≥1 ATS company chosen for the first vertical slice; profile, location, and benchmark configs version-controlled. **Stop and show the owner the audit before broad implementation.**

## Stage 1 — Operational discovery MVP · _Checkpoint B in progress_
**Goal:** a headless service that gives an early-application edge with nothing to maintain but a few adapters.
- Greenhouse / Lever / Ashby adapters + manual URL/text intake
- Normalize, dedupe (idempotent), source-health model
- Deterministic blockers → structured LLM evaluation (4 outputs) → SQLite
- Scan every 6h; one consolidated morning digest; optional urgent alert
- Review CLI + CSV exports

**Checkpoints:** B — one-source vertical slice working end-to-end (Databricks/Greenhouse local slice implemented; LLM evaluator still pending) · C — all three adapters + health + schedule + review CLI · D — benchmark calibration + live digest.
**Exit (PRD §10.2):** the 12-point acceptance test passes, incl. ≥95% recall on owner-labelled Apply/Consider roles and zero silent connector failures. **Stop and wait for explicit approval before Stage 2.**

## Stage 1.0 → 1.5 — Refinement + online opportunity list · _live, in progress (2026-06)_
**Status:** 1.0 (the daily email agent) is **shipped and operating**. 1.5 is the active phase. Goal: make the matching trustworthy and give the owner an online place to see and act on leads — *before* building the full tracker.
- **Search refinement / calibration:** strict monotonic band thresholds (DECISIONS #61: 80+ apply_now · 70–79 consider · 60–69 stretch · <60 skip — no post-hoc overrides), general function-gate fixes (kill keyword false-positives like Recruiter/SRE), required-credential down-ranking, multi-location dedup (B-02). Driven by owner calibration notes from live digests.
- **User testing:** owner runs the daily digest, flags misses; tune to acceptable live precision.
- **Web app — the full "Sextant" 4-page app (simple version), owner decision 2026-07-08.** Next.js + Supabase Postgres + Vercel, single-user. All four pages ship in 1.5 as the *simple* version: **Potential Matches** (daily digest online + role-detail evidence view + skipped/audit view), **To Apply** (shortlist), **Applied** (internal pipeline tracker — table, stages, next-action), **Profile** (read-only display of the current search criteria). Reads the agent's real data/logic; approval gate on every move; keeps all current rules. Design ref: `docs/design/sextant/`; build brief: `docs/briefs/webapp-build-brief.md`. Gated on the calibration stale-score fix landing first.

## Stage 2.0 — Optimize the app · _after 1.5_
Analytics/metrics, kanban, editable criteria in the UI, salary-anchoring, conversion analysis by CV version, advanced tracker features, light theme — the *optimization* layer on top of the simple 1.5 app. (Roadmap note: the tracker itself moved into 1.5 as a simple form; 2.0 is now "make the app better," not "build the tracker.")

## Stage 2.5 — Feedback-signal analytics · _after 2.0_ (backlog B-23)
Learn from the owner's own pipeline actions as graded quality signals: actioning a recommendation nudges *similar* roles higher, and a ladder of positive evidence — **hotlist < mark-applied < interview** — feeds the scoring, with dismiss/no-action as weak negative. A personalization layer on the calibrated evaluator. Guardrail: learned signals stay subordinate to the hard gates (location/level/blockers) and the strict monotonic bands — a learned preference never overrides a blocker. Needs 1.5 action history first.

## Stage 3 — Gmail-assisted updates · _after Stage 2 is stable_
Read-only Gmail OAuth → classify → suggest status updates in a review queue. No email-derived update changes state before approval. Disconnect/delete flow included.

## Stage 4 — Future (not approved)
CV/cover-letter copilot · interview-prep packs · outreach drafts · conversion analysis by CV version · discovery beyond the watchlist. Never: auto-apply.

## Productization track — External multi-user product · _separate track, after 2.0_ (backlog B-24)
Turn the single-user tool into a portfolio-grade external product: email login (owner-controlled access), a conversational intake agent that interviews a new user (citizenship, visa/work-auth, target roles + level, CV upload) to build their profile + watchlist, and a few sample-role ratings to seed per-user calibration. Demonstrates the project as a real product, not a personal tool. Large scope jump (multi-tenancy, per-user isolation, CV parsing, per-user calibration) — only after the single-user product is genuinely good.

---

### Guiding constraints
- Build a working **vertical slice** before broad coverage.
- **Deterministic first**, LLM only for semantics.
- **Fail loudly** — no silent zero-job scans.
- **Human approval** gates every consequential action.
- **Timebox.** Stop after Stage 1 if it is already delivering value; the search comes first.
