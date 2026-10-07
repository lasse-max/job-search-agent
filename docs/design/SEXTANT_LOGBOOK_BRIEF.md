# Sextant · Design pass 2 · "Logbook" brief

*Owner: Lasse · Written by Otto · 1 Oct 2026 · Status: direction chosen (day logbook). Lasse refines it in Claude Design and brings back the screens in section 9. Otto then writes the builder brief.*

**Attach when you open Claude Design:**

- `docs/design/directions/e-logbook-v3.png`: the starting point, revised after the Gemini review.
- `docs/design/directions/e-logbook-v3.html`: exact tokens and markup.
- `e-logbook-v2-day.png`: the denser 10-column version, for comparison.
- `docs/design/directions/logbook-pages/01` to `08`: Otto's mockups of the remaining screens, as HTML and PNG. They cover the evidence drawer (built for scoring v2), Mark to apply, To apply, Applied, the Applied drawer, Profile, Add a role and Login.

**Note (7 Oct):** scoring v2 (`docs/briefs/scoring-v2-core-job.md`) will replace the numeric Fit bands with a verdict (Strong / Good / Stretch / No) and fold "Screening odds" into it. The Matches column set changes once v2 passes its evaluation, so the builder brief waits for that.
- `docs/design/2026-10_design-audit.md`: what's wrong today.
- `docs/design/sextant/screenshots/`: the current app, every page.

---

## 1. The product in one paragraph

Sextant is a private, single-user job-search tool. Every morning an agent scans about 10,000 postings across 50 companies. AI scores each role against the owner's profile, and Sextant shows the results. The owner scans the list, opens the evidence, and **marks** roles to apply to. Nothing moves without a click. The pipeline runs Matches → To apply → Applied. Profile shows the search settings, and Add a role covers postings the scan can't reach. It's used daily on a laptop, and it's shown in interviews as a portfolio piece. **Clarity and scanning speed come first. Flair comes second.**

## 2. Why a second design pass

The current build is the 2026 "premium dark dashboard" template: navy, a teal accent, a Newsreader headline, mono uppercase labels, boxes around everything and seven pills per card. It also fails on legibility:

- The main button is 2.81:1 contrast.
- 70 % of the text is under 12 px.
- Source health is set at 8.5 px.

Full findings are in the audit.

## 3. The direction: a ship's logbook, by day

A deck log is a ruled book. Each entry gets one line, written in a fixed order. The important number goes in the margin. Headings are stamped wide, and colour is used only for things that mean something at sea, like buoys and chart water. That maps closely onto the product: **each role is a log entry**, fit is written in the margin, and the bands are the only colour.

**What the look must not become:** no anchors, compass roses, rope, wood grain, parchment or "vintage" textures. The nautical world shows through ruling, structure and colour logic, never through illustration.

## 4. Materials: colour with one job each

| Material | Token | Hex | Job |
|---|---|---|---|
| Paper | `page` | `#F3F4F1` | The page |
| Log sheet | `surface` | `#FFFFFF` | The table and the open entry. Raised surfaces step up in tone. No drop shadows. |
| Ruling | `rule` | `#E1E4E0` | Lines between entries only. The header rule and the margin double rule use ink. |
| Ink | `ink` | `#101820` | Text, the top bar, **the primary button** (white text, 17.9:1) |
| Pencil | `ink-2` | `#4A5560` | Secondary text (7.6:1 on white) |
| Sea green | `apply` | `#0E7352`, tint `#E4F3EC` | **Apply now band only**, plus "in your favour" notes (in band, why it fits) |
| Chart blue | `consider` | `#1D5BA3`, tint `#E6EFF8` | **Consider band only** |
| Buoy amber | `stretch` | `#8F5400`, tint `#FAF0DC` | **Stretch band only**, plus caution (visa needed, above band, watch out for) |
| Signal red | `warn` | `#B3261E` | Hard blockers and failures only |

**Rule:** the primary action is never coloured. It's solid ink, so colour always means a band or a warning, never "click me". Every text colour is at least 4.5:1 against its background.

## 5. Type: one family, three widths

**Archivo** (Google Fonts, variable width axis). The width does the work a second typeface usually would.

| Role | Setting |
|---|---|
| Page titles, wordmark | Archivo **Expanded** (`wdth 125`), 800, about 38 px, tight tracking |
| Words: UI and body | Archivo Normal (`wdth 100`), 400 to 700, 14 to 15.5 px |
| Numbers: fit, counts, dates, "4 of 5" | Archivo **Condensed** (`wdth 78`), tabular figures. The look of an instrument readout. |

Sentence case everywhere. **No all-caps labels, no letter-spaced micro-labels, no monospace.** The minimum is 12 px for anything you need to read.

## 6. Layout system

- **Bridge bar** (top, ink). Wordmark, then Matches, To apply and Applied with live counts, then Add a role and Profile. On the right: scan time and reach, and **source health**: amber, at least 13 px, always visible when something is degraded.
- **Page head.** Wide title, then a one-line summary with the band swatches ("28 apply now, 46 consider, 21 stretch").
- **Toolbar.** Real controls only: the band filter, search, sort, a link to skipped roles, and a `?` Shortcuts button. No pseudo-controls.
- **The log**, revised after the Gemini review:
  - **Five core columns:** Fit, Role, Screening odds, Career value, Level, plus an action that appears on hover or focus.
  - **The Role cell stacks two lines.** Line 1 is the company in bold, then location, any visa flag and posting age in pencil. Line 2 is the role title, with the full width to itself.
  - **Group headers** are a band-coloured swatch and label with the count. No tinted banners.
  - **Rows** are about 60 px tall, separated by very faint ruling (`#EDEFEC`) and whitespace, with a background change on hover. Keep the faint ruling: across 95 entries a day it still helps the eye track a row.
  - No cards and no boxes inside boxes.
- **The open entry.** It expands inline, with a 4 px left mark in the band colour. It holds three things: "Why it fits", "Watch out for", and the actions (Mark to apply, Full evidence, Open posting). Evidence ("4 of 5 requirements"), feasibility and model confidence go in one quiet line underneath.
- **Keyboard help.** `?` opens a small shortcuts overlay. The open entry shows only its own key (`A` on the button). No permanent legend.
- **Corner radius** 10 to 14 px on containers and controls. Rows and cells stay square.

## 7. Signature moments (one per screen; keep to these)

1. **Matches: the margin.** Fit written large in condensed numerals with a short bar in the band colour. The bar's scale runs from 60 to 100, so differences show. It's the only bold thing on the page.
2. **Mark to apply: the entry.** It's the human-approval gate, so it gets the one deliberate moment. The row confirms ("Marked, moved to To apply"), the To apply count in the bridge bar ticks up, and the row leaves the list. About 220 ms, with Undo for 5 s.
3. **Applied: the log, literally.** Stage history is an immutable, timestamped log ("12 Jun, recruiter screen → interviewing"). Show that it can't be edited, without a padlock icon.
4. **Profile: the ship's particulars.** The search settings set out like a particulars page: plain key and value rows in two columns, no nested panels. **Tier-weighted coverage leads**, not the blended percentage.

## 8. Rules (non-negotiable for the build)

- **Four separate signals, never one blended score:** Fit, Screening odds, Career value, Level. Evidence and freshness support them.
- **Nothing auto-advances.** Every pipeline move is an explicit click or key. Dismiss and Snooze appear only once they work; no disabled placeholders.
- **Fail loud on source health.** Visible in the bridge bar, and listed per source in Profile at full readable size.
- **Accessibility:** text contrast at least 4.5:1 (3:1 from 24 px), minimum 12 px, visible keyboard focus, real buttons and labels, drawers as proper dialogs (Esc closes, focus moves in and back).
- **Keyboard:** J and K move, Enter opens evidence, A marks to apply, Esc closes, / focuses search, ? shows the shortcuts. The shortcuts overlay must match what's built.
- **Motion:** one curve, `cubic-bezier(0.16, 1, 0.3, 1)` (from `design-rules.md`), 160 to 220 ms, used only for row expand, row hover, the evidence drawer and the Mark to apply moment. No staggered list entrances and no press-scale on every button: it's a daily scanning tool. With reduced motion on, everything cuts instantly.
- **Copy:** plain, sentence case. No em dashes, no emoji, no engineering jargon (version strings, "calibrated evaluator", backlog IDs, Supabase). Empty and error states say what to do next.
- **Decoration:** no gradients, glow, glass, icons in coloured circles or texture. The ruling is the only ornament.
- **Width:** desktop-first at 1440, and it must still work at 1280. 1024 can scroll horizontally on the log; it must not break.

**About the new metrics:**

- **Evidence** ("4 of 5") counts the job requirements backed by strong evidence. It uses data the app already stores, so it can ship with the restyle. It lives in the open entry, not as a column.
- **Screening odds** and **Career value** need scoring changes (backlog **B-39**) and will arrive with the next evaluator update. Design them now. Until B-39 lands, the same two columns show **Feasible** and **Confidence**, so the layout has to hold both pairs.

## 9. What to bring back (so the builder can build it)

Every screen and state at 1440 × 900, day theme:

1. **Matches:** All view; one band filtered; a focused and opened entry; row hover; Stretch collapsed and expanded; quiet day (no new roles, scan still reported); skipped roles view; "older than 21 days" toggled on; data load error.
2. **Full evidence drawer:**
   - each requirement against the evidence, with strength;
   - gaps with mitigations;
   - hard blockers;
   - feasibility, level rationale and model confidence;
   - the actions.
3. **Mark to apply:** before, during and after, including Undo.
4. **To apply:** the list with notes (add or edit a note), Mark applied, Remove, empty state.
5. **Applied:**
   - the table with stage, applied date and week, next action and due date. Design for **empty** next action and due fields too, because they're often blank;
   - the row drawer with the immutable stage history and the original evaluation snapshot;
   - the empty state.
6. **Profile:** search criteria; tier-weighted coverage; per-source health list; versions de-emphasised.
7. **Add a role:** the three intake modes (link, pasted text, manual line); the queued state; "link failed, paste the text instead"; the watchlist suggestion.
8. **Login:** plain, owner-only, with an error state. No setup instructions on the page.
9. **Global:** bridge bar in its normal, degraded and failed states; the app error page.

Plus:

- a **token table** for colour, type and spacing;
- a **component sheet**: buttons, filter, select, search, kbd hints, group row, fit margin, rating segments, flags, drawer;
- **motion notes** for anything that differs from section 8.

## 10. Open questions for Lasse in Claude Design

- **Bridge bar:** keep it ink-dark or make it light? Dark frames the page well, but it's the only dark element.
- **Fit margin:** number plus bar, or number only?
- **Column name:** "Evidence" or "Proof"?
- **Company tier:** show it in the log (a small mark next to the name), or leave it only inside Career value?
- **Night theme:** it isn't part of this pass, but the tokens should allow one later.

## 11. What happens after

When the final design is back, Otto writes the builder brief in `docs/briefs/`. It's restyle only: `web/` components, styles and tokens, with no changes to data, scoring, auth or migrations, plus one shared navigation component. Cato reviews it against this brief and checks for regressions. B-39 follows separately with the next evaluator version bump.
