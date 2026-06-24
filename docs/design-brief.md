# Design Brief — Job Search Agent UI (for Claude Design)

*Paste this into Claude Design as the opening prompt, then refine. This is the Stage 2 web app — the visual layer over the headless engine. Source of truth: `docs/PRD.md` §5 (evaluation) and §11 (UI).*

## One-line intent
A calm, data-dense **operator dashboard** for a single power user to triage freshly-discovered roles each morning and manage their application pipeline — fast to scan, trustworthy because every recommendation is explained, and impossible to take a consequential action by accident.

## Aesthetic
Modern, high-contrast, generous whitespace despite density. Reference feel: **Linear / Vercel / Notion**. Not flashy. Color is used **only** to carry meaning — recommendation bands and source health — never decoration. Light **and** dark themes. Desktop-first at 1440px.

---

## Screen 1 — Opportunity Inbox (the core screen)
A review queue of unreviewed roles, sorted by **recommendation → company tier → first-seen time**.

**The central design idea: show four *separate* signals, never one blended score.** A high company brand or a good location must never visually mask a weak role fit. Each opportunity card shows them distinctly:

1. **Fit** — a 0–100 score with a confidence indicator.
2. **Feasibility** — a chip: `viable` (green) · `sponsorship required` (amber) · `uncertain` (grey) · `blocked` (red). Show the short note inline, e.g. *"Australia · viable · ~3-mo work lead time"* or *"US · sponsorship required."*
3. **Strategic priority** — company tier (T1/T2/T3) + freshness (`new today` / `recent`) + a **warm-path** marker when present.
4. **Recommendation** — a colored pill, the loudest element on the card: **Apply now** (green) · **Consider** (blue) · **Stretch** (amber) · **Skip** (grey) · **Blocked** (red).

Plus, on the card: company · title · location · first-seen + source-posted date · source link.

**Detail drawer (expand a card)** shows the evaluator's reasoning — this is what builds trust:
- **Alignments** — 2–4 rows of *job requirement → my evidence*, each tagged strong / medium / weak.
- **Gaps** — 1–3 rows, each with severity (low/med/high) + a one-line mitigation.
- **Blocker** callout if any; **uncertainties** if the evaluator flagged thin data.

**Actions per card:** Approve · Dismiss · Snooze · Mark duplicate · Open source. **Approve is the only action that creates a tracked application — make it feel deliberate and slightly weightier than the rest.** Dismiss asks for a one-tap reason (wrong function / level / location / visa / company priority).

**Filters bar:** company tier, location, role family, recommendation band, fit band, feasibility, source health, posting age.

## Screen 2 — Application Tracker
Default **table** view with a **kanban** toggle, over one underlying record.

- **Stages:** Preparing → Applied → Recruiter Screen → Interviewing → Final Round → Offer (+ Rejected / Withdrawn / Archived).
- **Fields:** company, role, location, job URL, stage, date found / applied, last activity, next action + due date, contact/referral, document refs, notes.
- An **immutable activity timeline** per application (stage changes, notes, emails, interviews) — visually a vertical history.
- A **stale flag** when there's no activity and no next action.
- **Metrics strip** on top: active pipeline by stage, applications this week, first-seen→applied time, conversion by role family / company tier.

## Screen 3 — System Health (compact)
A small panel, not a full page — because "fail loud" is a product principle: **source coverage** with status per company (`healthy` / `degraded` / `failing` / `unsupported`), last scan time, and any silent-zero or expected-volume anomalies surfaced prominently. A broken connector must never look like "no new roles today."

## Screen 4 — Settings (light)
Company watchlist + tiers, role-family rules, the location/visa policy matrix, and candidate-profile versions.

---

## Make these principles visible in the design
- **Human-approval gate** — Approve is the boundary between an opportunity and a tracked application; design it as an intentional act, not a one-pixel button next to Dismiss.
- **Explainability** — evidence and gaps are first-class, not hidden behind a number.
- **Fail loud** — source failures are surfaced, never swallowed.

## Deliverables to ask Claude Design for
1. Opportunity Inbox — the default queue **and** an expanded detail drawer (alignments + gaps).
2. Application Tracker — table view + kanban view + the metrics strip.
3. A small component set: opportunity card, fit score badge, feasibility chip, recommendation pill, source-health indicator, stage pill, alignment/gap row.
4. The recommendation-band and feasibility color system, in light + dark.

## Constraints
Single-user, authenticated; no public/marketing pages. Mirror the PRD surfaces. Designed to later import a real design system and to hand off to the builder for the Stage 2 build.
