# Job Search Agent — Web App Design Brief (3 pages)
*Paste into Claude design. Single-user private web app in the Layline brand. Design-first; build after.*

---

## PASTE-THIS PROMPT

> Design a calm, data-dense **single-user job-search web app** in the **Layline** brand (nautical chart-paper, dark theme — tokens below). **Three pages**, connected as a pipeline:
> **1) Potential Matches** — AI-scored roles (the same list the daily email sends), grouped by recommendation band, each with a fit score, chips, and an expandable "why it fits" evidence view; primary action **Mark to apply**.
> **2) To Apply** — the shortlist of roles I marked; primary action **Mark applied**.
> **3) Applied (Tracker)** — a table of roles I've applied to, tracking each through interview stages (a personal application pipeline tracker).
> Desktop-first, single focused user, no login/marketing chrome. Feel: a navigator's chart — precise, confident, uncluttered; one accent used sparingly; lots of quiet. Nothing moves between pages automatically — every transition is an explicit click.

---

## Who & why
One private user (me). Replaces a morning email digest + a spreadsheet. Flow: **see strong roles → shortlist the ones worth applying to → track the ones I applied to**, never losing control of a decision. Tone: *"velocity made good"* — real progress toward a destination.

## Brand tokens (Layline — dark)
- **Surface:** `#0a141c` (page), `#0d1a24` / `#13242f` (panels/cards) · **Lines:** `rgba(255,255,255,.08)`
- **Text:** ink `#eef0ec` · muted `#9fb0b6` · faint `#6f828a`
- **Accent — deep-water teal:** `#1f6f7c` (bright-on-dark `#57b6c4`)
- **Destination mark — rust:** `#b8472f` (bright `#e07a5c`) → reserve for **apply_now / primary action**
- **Success/viable:** `#5bbf9a` · **Stretch/caution gold:** `#c7a86a` · **Warn/issue:** `#ec6c41`
- **Type:** headings **Newsreader** (serif) · body/UI **IBM Plex Sans** · data/IDs/mono **IBM Plex Mono**
- Small radii (6–10px), hairline borders, generous whitespace, subtle shadows.

## Shared: the role object (real fields, so cards/detail have content)
Company · title · location(s) · department · company tier (1/2/3) · **fit score 0–100** · **confidence %** · **recommendation** (apply_now / consider / stretch) · **feasibility** (viable / sponsorship_required) · 1–3 **alignments** (JD requirement → my evidence, strength strong/med/weak) · 1–3 **gaps** (severity + mitigation) · 2–3 sentence summary · apply link · first-seen date.

## Left nav (persistent)
Layline wordmark + "find your layline" · **Potential Matches** · **To Apply** · **Applied** · (small) System health. A pipeline counter on each nav item (e.g. Matches 12 · To Apply 5 · Applied 8).

---

## Page 1 — Potential Matches  ★ design first
The daily digest, online. Best roles first.
- **Top bar:** date · summary counts ("1 apply · 7 consider · 3 stretch") · **scan-reach stat** ("Scanned 6,901 postings across 32 companies") · sort (fit / newest / tier) · filter (band, location, tier, company).
- **Grouped by band:** **Apply now** (rust accent) → **Consider** (teal) → **Stretch / reach** (gold, collapsed, labelled "scrutinize").
- **Role card:** company + title (serif) · **fit as a prominent badge** (number, colour-keyed to band) · chips: location · tier · feasibility · confidence · one-line summary · **expand** → top alignment (✓) + top gap (△). Actions: **Mark to apply** (primary, rust → moves to page 2) · Dismiss · Snooze · Open source ↗.
- **Source-health strip:** subtle amber banner if a feed degraded.
- **Optional toggle — "Skipped / all roles":** audit view showing everything evaluated incl. skip/blocked, each with band, fit, and a one-line *reason skipped* (off-function / off-location / over-level / required-credential / language) — so I can catch a good role wrongly filtered. (Not a 4th page — a toggle here.)
- **States:** loading · quiet-day ("no strong matches — top 5 by fit, for calibration") · degraded.

## Page 1b — Role detail (slide-over panel) ★ design with page 1
The differentiator: show *why*. Header (company · title · fit badge · confidence · recommendation · feasibility) → **evidence mapping** as aligned rows *"JD requirement → my evidence"* with a strength pip; **gaps** as rows (severity + mitigation); summary; apply link; posted/first-seen. Primary action: **Mark to apply**. Keep it readable and credible, not a wall of AI text.

## Page 2 — To Apply (shortlist)
Roles I flagged, pre-application — my working set.
- Lighter than page 1: a focused list (or simple board). Each item: company · title · fit · location · free-text note · age ("flagged 2d ago").
- **Primary action: Mark applied →** (moves to the Tracker). Secondary: open role, back to matches, remove.
- Small and calm — a curated handful, not a feed. Empty state: "Nothing shortlisted — mark roles from Potential Matches."

## Page 3 — Applied (Tracker)  *(internal working pipeline — not a vanity dashboard)*
The roles I've applied to, tracked through stages. **Reference:** a friend's tracker (hasse-job-search.netlify.app) is the shape, but his is *external/motivational* (weekly streak, "weeks with ≥2 applications" habit bar, interview-rate badge, salary-anchoring showpiece). **Make this internal instead** — a quiet tool that helps me *run* the search, not display it.
- **Keep from that reference:** the applications **table**, a compact **stage funnel**, an **Applied-on / calendar-week** column, and a **salary** column (useful for comparing offers internally).
- **Drop:** the weekly-streak gamification, the ≥2/week habit bar, the interview-rate vanity metric, and the salary-anchoring hero section.
- **Slim stat strip (quiet, not a dashboard):** Active · In interview · Offers · Closed — plain counts, small, top-right. No streaks, no charts-for-show.
- **Primary view: table.** Columns: Company · Role · Location · **Stage** · Applied on (+ CW) · **Next action** · Due · Contact/referral · Salary · Notes. Emphasis on **Next action + Due** — the working columns.
- **Stages** as a coloured pill progression: `preparing → applied → recruiter screen → interviewing → final round → offer / rejected / withdrawn`. Compact funnel of per-stage counts up top.
- **Row → detail drawer:** immutable timeline of stage changes (date-stamped), notes, contacts, document links, and the **original evaluation snapshot** from when it was shortlisted (fit, alignments, gaps — so I remember why I applied and can prep).
- Optional later: kanban by stage (design table first).
- Empty state: "Nothing applied yet — promote a role from To Apply."

## Pipeline & rules
`Potential Matches → (Mark to apply) → To Apply → (Mark applied) → Applied`. Every move is an explicit click; nothing auto-advances. Only "Mark applied" creates a tracked application record.

## Design priority
1. Page 1 (Potential Matches) + 1b (role detail) — the daily surface + the evidence differentiator.
2. Page 3 (Applied tracker) — table + stage pills + detail drawer.
3. Page 2 (To Apply) — lightest.

## Out of scope (don't design)
Login/auth screens, marketing pages, multi-user, mobile-first, analytics dashboards. Just the three pages + role detail.
