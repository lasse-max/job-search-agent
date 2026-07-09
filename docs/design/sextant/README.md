# Handoff: Sextant — Job-Search Navigator

## Overview
A calm, data-dense, **single-user** internal web app for tracking an AI-driven job search (Strategy & Operations roles). Nautical "chart-paper" dark theme. Four pages wired as a one-way pipeline — every move between pages is an explicit user click, nothing auto-advances:

**Potential Matches** (daily AI digest) → **To Apply** (shortlist) → **Applied** (pipeline tracker), plus a read-only **Profile** page showing the agent's search parameters.

No login, no marketing, no multi-user chrome, no analytics dashboards. Desktop-first (≥1280px). Deliberately quiet: no streaks, habit bars, or vanity metrics.

## About the Design Files
The files in this bundle are **design references created in HTML** — prototypes showing intended look and behavior, not production code to copy directly. The task is to **recreate these designs in the target codebase's existing environment** (React, Vue, Svelte, etc.) using its established patterns and libraries — or, if no environment exists yet, choose the most appropriate stack and implement the designs there.

The `.dc.html` files contain the full template markup (all inline styles = exact values) and a JS logic class with all sample data, state shape, and interaction handlers — read both.

## Fidelity
**High-fidelity.** Colors, typography, spacing, and interactions are final. Recreate pixel-perfectly. **`Sextant.dc.html` (dark) is the canonical design.** `Sextant Light.dc.html` is an optional light variant produced by a systematic palette swap — same layout, not required for v1.

## Design Tokens

### Colors (dark theme — canonical)
- Page background: `#0a141c`
- Panel background: `#0d1a24`
- Card background: `#13242f`
- Hairline borders: `rgba(255,255,255,.08)` (subtler dividers `.05`/`.06`, hover borders `.14`–`.28`)
- Ink (primary text): `#eef0ec`; secondary ink `#cfd8da`
- Muted text: `#9fb0b6`
- Faint text: `#6f828a` (disabled/zero: `#3d4c53`)
- Accent teal: `#1f6f7c` (deep) / `#57b6c4` (bright) / `#7fd0dc` (hover)
- Rust (destination mark — **reserved** for "Apply now" band + primary action buttons only): `#b8472f` (button) / `#cf5638` (button hover) / `#e07a5c` (text/badges)
- Success/viable green: `#5bbf9a`
- Stretch/caution gold: `#c7a86a`
- Warn/overdue: `#ec6c41`
- Modal backdrop: `rgba(4,10,14,.6)`
- Optional chart-grid overlay: 1px lines `rgba(87,182,196,.028)`, 56px grid, fixed, pointer-events none (toggleable)

### Typography
- Headings: **Newsreader** (serif), weight 500; page titles 27px, drawer titles 22px; wordmark italic 21px
- Body/UI: **IBM Plex Sans** 400/500/600; body 12.5–13px, card titles 14.5–15px
- Data/mono: **IBM Plex Mono** 400/500; fit scores 19–20px, chips 10.5px, column headers 9.5–10px uppercase letter-spacing 1px, meta lines 11–11.5px
- All from Google Fonts.

### Spacing & shape
- Radii: 6px (buttons, chips, pills), 8px (badges, panels, inner blocks), 10px (cards, tables)
- Page padding: 32px 40px; content max-widths: Matches 1020px, To Apply 860px, Applied 1280px, Profile 920px
- Card padding 16–18px; vertical card gap 10px
- No drop shadows except drawers: `-24px 0 60px rgba(0,0,0,.45)`

### Semantic color rules
- Band colors: Apply now = rust `#e07a5c`, Consider = teal `#57b6c4`, Stretch/reach = gold `#c7a86a`
- Fit score color = its band color (standalone fit numbers: ≥85 rust, 65–84 teal, 45–64 gold, else faint)
- Percentage chips (feasibility, confidence): ≥70% green `#5bbf9a`, 40–69% gold `#c7a86a`, <40% warn `#ec6c41`; chip border = same color at ~22% alpha
- Tier chip: Tier 1 = teal, Tier 2 = muted
- Evidence strength pips: strong = green, partial = gold, weak = warn
- Stage pills (outlined, transparent bg, mono 10px): preparing `#9fb0b6`, applied `#1f6f7c`, recruiter screen `#57b6c4`, interviewing `#c7a86a`, final round `#e07a5c`, offer `#5bbf9a`, rejected/withdrawn `#6f828a`
- Due dates: overdue = warn, due soon = gold, ok = muted, none = faint

## Screens / Views

### Persistent left nav (224px, all pages)
- Wordmark: "Sextant" (Newsreader italic 21px) + 7px teal rotated-square diamond
- Items: Potential Matches · To Apply · Applied · Profile, each with a **live count** (mono, right-aligned; Profile has none). Active item: bg `rgba(87,182,196,.10)`, ink text, teal count
- Footer (mono 10.5px faint, above hairline): "last scan · today 06:12", "6,901 postings · 32 cos.", "next scan · tomorrow 06:00"

### Page 1 — Potential Matches
- Header: serif title + mono date line ("Wed 8 Jul 2026 · digest generated 06:12"); top-right ghost button toggles the **audit view** ("skipped / all roles · N" ↔ "← back to matches")
- Summary bar (panel): colored-dot counts "1 apply · 7 consider · 3 stretch", divider, mono scan-reach stat ("scanned 6,901 postings across 32 companies"); right: two mono chips "sort · fit ↓", "filter · all" (visual affordances)
- **Bands** with headers (colored 14×3px tick + uppercase label letter-spacing 1.8px + count + hairline rule): Apply now (rust) → Consider (teal) → Stretch/reach (gold, **collapsed by default** with a dashed-border note "3 stretch roles collapsed…" and an expand/collapse caret)
- **Role card** (flex row): 54px square fit badge (mono score + "FIT" microlabel, 1px border in band color at ~40% alpha) · body (company 600 + title, chip row, one-line muted summary, optional expanded block) · right action column
  - Chips (mono 10.5px, 1px border): location (muted) · Tier N (teal if T1) · "feasibility NN%" · "confidence NN%" (percentage-colored, see rules above)
  - Expanded block (inner panel `#0d1a24`): "✓ top alignment" (green check, ink text), "△ top gap" (gold triangle, muted text), teal link "Full evidence →" opens slide-over
  - Actions: **Mark to apply** (rust solid, primary) · Dismiss + Snooze (outlined ghost buttons: 1px `rgba(255,255,255,.14)`, bg `rgba(255,255,255,.03)`) · "Source ↗" link · "▾ details / ▴ less" mono caret toggling the expanded block
- **Audit view** (replaces bands): "Skipped / all evaluated" list — grid rows fit (mono) · company · title · skip reason (mono faint), e.g. "below fit floor (40)", "location filter — onsite Zürich", "duplicate — evaluated 30 Jun", "snoozed by you until 15 Jul"; footer row "…and 6,874 more below the fit floor (40) — not stored"
- **Quiet-day state** (flag): gold-tinted banner "No strong matches today — showing the top 5 by fit." with a single ungrouped "Top 5 by fit" band

### Role-detail slide-over (the differentiator)
490px right panel over dimmed backdrop; slide-in 220ms ease + backdrop fade 180ms.
- Header: band label (uppercase, band color) + ✕; company — title (serif 22px) with 56px fit badge right; chip row; summary
- **"Why it fits"** section (rule header + mono hint "JD requirement → your evidence"): rows on `#13242f` — strength pip (8px dot) · JD requirement (muted 12px) · "→ your evidence" (ink 12.5px, teal arrow) · strength word (mono 9.5px, pip color)
- **"Gaps & mitigations"** (gold header): gold-bordered rows — △ · gap (ink) · mitigation (muted)
- Footer (hairline top): Mark to apply (rust) · Dismiss · Snooze (ghost) · "Open source ↗" right

### Page 2 — To Apply
Lighter list on `#0d1a24` rows: fit (mono, colored) · company + title + mono location · free-text note (italic muted; empty = "add a note…" placeholder) · age ("flagged 2d ago", mono faint) · **Mark applied** (rust) + Remove (text).
Empty state (centered, serif italic): "Nothing shortlisted." / "Mark roles from Potential Matches." (link)

### Page 3 — Applied
- Header right: **slim stat strip** — Active · In interview · Offers · Closed as plain mono counts with hairline separators (no charts, no vanity metrics)
- **Compact funnel** (panel): 6 stage segments (preparing → offer), each mono count (faint if 0) + uppercase microlabel + 3px bar in stage color, width 10 + count×26 px
- **Table** (grid, min-width 1140px, horizontal scroll): Company · Role · Location · Stage pill · Applied (date + ISO week, e.g. "12 Jun · W24") · **Next action** (ink, 500 — emphasized) · **Due** (mono, tone-colored — emphasized) · Contact · Salary · Notes. Rows: hairline-top, hover `rgba(255,255,255,.025)`, click opens drawer. Closed rows (rejected/withdrawn) render fully faint.
- **Row drawer** (470px): stage pill + ✕; serif title; 2-col meta grid (Applied / Contact / Next action / Due); **Stage history** — "immutable" tag, vertical timeline (teal dots on hairline spine, mono dates, e.g. "recruiter screen → interviewing · panel scheduled 11 Jul"); **Original evaluation** — snapshot panel with fit-at-evaluation, ✓ alignments, △ gaps ("why you applied")
- Empty state: "Nothing applied yet." / "Promote a role from To Apply."

### Page 4 — Profile (read-only)
Subtitle: "parameters the agent scans with · read-only — set in agent config". 2-col grid of panels, each with teal uppercase header over hairline and 120px-label/value rows (labels mono 10px uppercase faint):
1. **Candidate & authorization** — work auth, base, acceptable locations, onsite max, relocation
2. **Target roles** — teal role chips (Strategy & Operations, Business Operations, Chief of Staff (GTM), GTM/Sales Strategy), seniority band, exclusions
3. **Compensation** — base target $165–200k, floor $155k ("hard" in warn), equity
4. **Scoring & bands** — thresholds in band colors (apply ≥85 rust, consider 65–84 teal, stretch 45–64 gold), fit floor 40, definitions: feasibility = "% chance the application is viable (location, auth, seniority, comp)", confidence = "% model certainty in the fit estimate"
5. **Sources & cadence** (full width) — 32 companies (14 T1 · 18 T2), boards, daily 06:00 ET scan, snooze default 7d, dedupe

## Interactions & Behavior
- Nav clicks switch pages and close any open drawer/slide-over
- **Mark to apply** (card or slide-over): removes role from Matches, prepends to To Apply shortlist ("flagged today", carrying fit/location/alignment/gap snapshot); closes slide-over if open
- **Dismiss / Snooze**: removes role from Matches, appends to the skipped/audit list with reason ("dismissed by you — today" / "snoozed by you until <date+7d>")
- **Mark applied**: removes from shortlist, prepends to Applied at stage `preparing` with history entry "Promoted from shortlist → preparing" and the evaluation snapshot
- All nav counts, band counts, summary counts, stat strip, and funnel recompute live from state
- Card "▾ details" toggles the alignment/gap block (one card expanded at a time)
- Stretch band collapse/expand toggle; audit view toggle
- Drawers close via ✕ or backdrop click; animations: slide-in `translateX(28px)→0` 220ms ease, backdrop fade 180ms
- Buttons/links have defined hover states (see inline `style-hover` attributes in the files)
- **Nothing auto-advances**; history entries are append-only (immutable)

## State Management
- `page` ('matches' | 'toapply' | 'applied' | 'profile'), `auditOn`, `stretchOpen`, `expandedId`, `detailId`, `drawerId`
- Collections: `matches[]` (id, band, fit, company, title, loc, tier, feas%, conf%, summary, align, gap, evidence[{req, mine, strength}], gaps[{gap, mit}]), `skipped[]` (fit, company, title, reason), `shortlist[]` (fit, company, title, loc, note, age, snapAligns, snapGaps), `applied[]` (company, role, loc, stage, appliedOn, next, due, dueTone, contact, salary, notes, history[{d, e}], snapDate, snapFit, snapAligns, snapGaps)
- Derived: band groupings, nav counts (Applied count excludes rejected/withdrawn), stat strip, funnel counts
- Two display flags (exposed as tweakable props in the prototype): `quietDay` (default false), `chartGrid` (default true)
- Prototype is client-state only; production persistence is up to the implementer (single user — local DB/file is fine)

## Assets
None — no images or icon fonts. Glyphs are text characters (✓ △ ▾ ▴ ✕ → ↗ ·); the wordmark diamond is a CSS rotated square. Fonts from Google Fonts: Newsreader, IBM Plex Sans, IBM Plex Mono.

## Files
- `Sextant.dc.html` — **canonical dark design**: full template (inline styles = spec) + logic class (data shapes, handlers, color functions `fitColor` / `pctColor` / stage map)
- `Sextant Light.dc.html` — optional light "day-chart" variant (systematic palette swap; page `#f2eee1`, panels `#faf7ec`, ink `#1c2a31`, accents re-anchored darker)
- `screenshots/` — reference captures of the dark design: 01 Potential Matches · 02 role-detail slide-over · 03 audit/skipped view · 04 To Apply · 05 Applied table · 06 Applied row drawer · 07 Profile
