# Stage 2 (2.0) — Design Brief
*For Claude design / mockups. Design first, build after. Single-user private web app — the operating surface for the job-search agent.*

---

## Paste-this prompt (short version)

> Design a calm, data-dense **single-user job-search web app** in the **Layline** brand (nautical chart-paper, dark theme). Three core screens — **New Opportunities** (an inbox of AI-evaluated roles), **Active Opportunities** (a shortlist of roles I've flagged), and **Application Tracker** (a pipeline of roles I've applied to). Desktop-first. Use the brand tokens below. Priority screen to nail first: **New Opportunities + the role-detail panel.** Feel: precise, confident, uncluttered — like a navigator's chart, not a busy SaaS dashboard.

---

## Who & why
- **One user (me).** Private tool, no onboarding, no marketing, no multi-tenant chrome.
- Replaces a morning email digest + a spreadsheet. The job: *see the few strong roles, shortlist them, track the ones I apply to* — without losing control of any decision.
- Tone: **"velocity made good"** — real progress toward a destination. Calm, sharp, trustworthy. Information-dense but never noisy.

## Brand system (Layline)
**Colors — dark (primary theme):**
- Surface / bg: `#0a141c` (outer), `#0d1a24` / `#13242f` (panels)
- Ink (text): `#eef0ec` · muted: `#9fb0b6` · faint: `#6f828a`
- **Accent — deep-water teal:** `#1f6f7c` (bright-on-dark `#57b6c4`)
- **Destination mark — rust:** `#b8472f` (bright `#e07a5c`) → reserve for *the top action / apply_now*
- Success / viable: `#5bbf9a` · Warn / issue: `#ec6c41` · Stretch / caution gold: `#c7a86a`
- Lines: `rgba(255,255,255,.08)`

*(Light variant exists if you want a paper mode: paper `#f4f2ec`, ink `#13242f`, same teal/rust.)*

**Type:** Headings — **Newsreader** (serif, elegant). Body/UI — **IBM Plex Sans**. Data / IDs / commands — **IBM Plex Mono**.
**Shape:** small radii (2–6px), thin hairline borders, generous whitespace, subtle shadows. Chart-paper restraint — one accent, used sparingly.

## Recurring data per role (so cards/detail have real content)
Company · title · location · department · **company tier** (1/2/3) · **fit score 0–100** · **confidence %** · **recommendation** (apply_now / consider / stretch) · **feasibility** (viable / sponsorship_required / uncertain) · 1–3 **alignments** (JD requirement → my evidence, strength) · 1–3 **gaps** (severity, mitigation) · a 2–3 sentence summary · source link.

---

## Screen 1 — New Opportunities (the inbox) ★ design first
**Purpose:** the daily surface — newly evaluated roles, best first.
- **Layout:** left nav (3 screens + System health) · main column of role cards grouped by band: **Apply now** (rust accent) → **Consider** (teal) → **Stretch / reach** (gold, collapsed, labelled "calibration in progress — scrutinize").
- **Role card:** company + title (serif), **fit as a prominent badge** (the number, colour-keyed to band), chips for location · tier · feasibility · confidence. One-line summary. Expand → top alignment (✓) + top gap (△). Actions: **Interested** (primary, moves to Active), **Dismiss**, **Snooze**, **Open source ↗**.
- **Top bar:** date, summary count ("1 apply · 4 consider · 6 stretch · 1 source issue"), sort (fit / newest / tier), filter (band, location, tier).
- **Source-health strip:** subtle banner if a feed is degraded (e.g. "[source] ATS: 0 jobs").
- **States:** loading, empty ("no new roles this cycle — here are the top 5 for calibration"), degraded.

## Screen 1b — Role detail (panel or page) ★ design with screen 1
The differentiator — show *why*. Slide-over panel or full page:
- Header: company · title · fit badge · confidence · recommendation · feasibility.
- **Evidence mapping:** alignments as aligned rows — *"JD requirement → my evidence"* with a strength pip (strong/medium/weak). Gaps as rows with severity + mitigation. This is the heart — make it readable and credible, not a wall.
- Summary, source link, posted/first-seen dates.
- Primary action: **Mark interested** → Active.

## Screen 2 — Active Opportunities (shortlist)
**Purpose:** roles I've flagged but not yet applied to — my working set.
- **Layout:** lighter than the inbox — a focused list or simple board. Each item: company · title · fit · location · a free-text note · age ("flagged 2d ago").
- Primary action: **Applied →** (promotes to the Tracker, creates an application record). Secondary: back to inbox, dismiss.
- Keep it small and calm — this is a curated handful, not a feed.

## Screen 3 — Application Tracker
**Purpose:** the pipeline of things I've actually applied to (Hasse-style).
- **Primary view: table.** Columns: Company · Role · Location · **Stage** · Date applied · Last activity · **Next action** · Due · Contact · Notes.
- **Stages** as a clear status/pill progression: `preparing → applied → recruiter screen → interviewing → final round → offer / rejected / withdrawn`. Colour-key stages.
- Row → detail drawer: full history (immutable timeline of stage changes), notes, contacts, doc links, and the *original evaluation snapshot* from when it was approved.
- Optional later: kanban by stage. Table first.
- **States:** empty ("nothing applied yet — promote a role from Active"), per-stage counts up top.

## Cross-cutting
- **Left nav:** New Opportunities · Active · Tracker · System health (coverage, last scan, source failures, cost). Brand wordmark + "find your layline."
- **The one hard rule (reflect in UI):** *nothing consequential happens automatically.* Moving a role between New → Active → Applied is always an explicit click. "Applied" is the only action that creates a tracked record.
- **Empty/quiet states matter** — this app is often calm; quiet should feel intentional, not broken.
- Desktop-first (single user, focused sessions); graceful at tablet width.

## Design priority order
1. **New Opportunities + Role detail** (the daily surface + the evidence differentiator).
2. **Application Tracker** (table + stage pills + detail drawer).
3. **Active Opportunities** (lightest screen).
4. Nav shell + System health.

## Out of scope (don't design)
Auth/login screens, settings beyond a watchlist view, mobile-first layouts, kanban v1, analytics dashboards, anything multi-user. Keep it to the three screens + detail views.
