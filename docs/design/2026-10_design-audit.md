# Sextant design audit: does it look AI-made?

*Otto · 1 Oct 2026 · Step 1 of `docs/briefs/otto-design-pass-anti-ai-look.md` · Read-only: no code, config or data changed.*

## 1. Verdict

**Yes, it reads as the 2026 "premium dark dashboard" template.** It's a capable build, but the structure underneath is a stock dark dashboard: navy ground, a teal accent, a Newsreader headline, and mono uppercase labels on everything. Hairline boxes sit around every group, and pills of equal weight sit on every card. The nautical idea only shows in the name, a 7 px diamond and a 2.8 %-opacity grid.

**The bigger problem is legibility, not taste.** These are accessibility failures on the things that matter most:

- The **primary action button fails contrast on every page except login**. "Mark to apply", the human-approval gate, is 2.81:1.
- **70 % of the text on Potential Matches is smaller than 12 px.**
- **Source health, the signal we promised would "fail loud", is set in 8.5 px.**

These should be fixed whatever direction is chosen (section 7).

**Top five, in order:**

1. F-01: the primary buttons fail AA (2.58–2.81:1).
2. F-02 and F-03: most readable text is under 12 px, and the most-used text colour fails AA on cards and panels.
3. F-09: there's no hierarchy on Potential Matches. 74 identical cards, 28 of them "Apply now", and nothing says "start here".
4. F-05 and F-07: mono is the main typeface, and borders do all the structural work.
5. F-13: the nav is implemented five times and has already drifted. The Add a role page has no Profile link.

## 2. Method and evidence

- **Live app:** `job-search-agent-gilt-rho.vercel.app`, signed in by Lasse on 1 Oct 2026, emulated at 1440 × 900 (the design is desktop-first). Data was live: digest generated 1 Oct 03:31, 10,501 postings across 50 companies, 28 apply / 46 consider / 21 stretch.
- **Screenshots:**
  - **S1 (live):** Potential Matches, top of page, first card expanded.
  - The browser pane stopped repainting after S1 because the window was covered. So the other pages were measured from the **live DOM**: computed font size, family, borders and colours of every visible text element.
  - Layout is cross-checked against the canonical captures in `docs/design/sextant/screenshots/01–07`. The built pages match those layouts.
  - I can't save browser captures into the repo from this environment. If you want image files next to this doc, a Cmd+Shift+4 capture of each page will do.
- **Code read:** `web/app/globals.css`, `web/tailwind.config.ts` and every page component. File and line references below are at `main` `6c5c957`.
- **Contrast:** WCAG 2.x relative-luminance ratios, computed from the actual tokens. Alpha colours are blended over the real background first.

**Per-page measurements (live DOM)**

"Bordered" means a visible element with a border and a corner radius.

| Page | Text elements | Under 12 px | Set in mono | Bordered boxes |
|---|---|---|---|---|
| Potential Matches (74 cards rendered) | 1,294 | **902 (70 %)** | **834 (64 %)** | **821** |
| Role detail slide-over | 53 | 20 (38 %) | not measured | 19 |
| To Apply (empty today) | 13 | 4 | 4 | 0 |
| Applied (8 rows) | 122 | **81 (66 %)** | 61 (50 %) | 10 |
| Profile | 388 | **218 (56 %)** | 169 (44 %) | **136, of which 130 are nested in another box** |
| Add a role | 22 | 5 | not measured | 10 |
| Login | from code | 2 labels at 10 px | 2 | 3 |

**Contrast of the real tokens**

| Foreground | on page `#0a141c` | on panel `#0d1a24` | on card `#13242f` | Verdict |
|---|---|---|---|---|
| ink `#eef0ec` | 16.2 | 15.4 | 13.9 | pass |
| muted `#9fb0b6` | 8.3 | 7.9 | 7.1 | pass |
| **faint `#6f828a`**, the most-used text colour (74 uses) | 4.63 | **4.40** | **3.96** | **fails on panels and cards** |
| `white/30` (owner email in nav) | 2.66 | 2.71 | 2.69 | fail |
| `white/20` (zero counts on Applied) | 1.85 | 1.88 | 1.91 | fail |
| faint "FIT" label on a tinted fit badge | | | 3.3–3.5 | fail (and 8 px) |
| teal / gold / green / warn / rust as text | 6.0–8.3 | 5.7–7.9 | 5.1–7.1 | pass |
| **white/95 on rust `#e07a5c`** ("Mark to apply", "Mark applied", error retry) | button fill | | | **2.81, fail** |
| **ink on rust `#e07a5c`** ("Queue evaluation") | button fill | | | **2.58, fail** |
| white on `#b8472f` (login "Sign in") | button fill | | | 5.28, pass |

`#3d4c53` from the design README isn't used in the built code, but `white/20` plays the same role and fails worse.

## 3. Checklist scorecard

**P** = present, **½** = partly, **–** = absent.

| # | Item | Matches | Detail | To Apply | Applied | Profile | Add a role | Login |
|---|---|---|---|---|---|---|---|---|
| 1 | Premium dark recipe | P | P | P | P | P | P | P |
| 2 | Boxes everywhere | P | P | P | ½ | P | ½ | ½ |
| 3 | Chip soup | P | P | – | ½ | P | – | – |
| 4 | Symmetric stat strips | ½ | – | – | P | P | – | – |
| 5 | Pseudo-controls | P | P | – | – | – | – | – |
| 6 | Icon circles, emoji, decorative glyphs | ½ | ½ | – | ½ | ½ | – | – |
| 7 | Overused fonts | P | P | P | P | P | P | P |
| 8 | Gradient, glow, glass as decoration | ½ | – | ½ | ½ | ½ | – | – |
| 9 | No hierarchy | P | ½ | ½ | P | P | ½ | – |
| 10 | Motion: none or random | P | P | ½ | P | ½ | ½ | ½ |
| 11 | Generic copy and em dashes | ½ | P | ½ | ½ | ½ | ½ | ½ |
| 12 | Accessibility misses | P | P | P | P | P | P | ½ |

**Checking the brief's prior read** ("hits 1, 2, 3, 4, 5, 7 and 12 clearly"):

- **Confirmed:** 1, 2, 3, 4, 5, 7 and 12.
- **Add 9 (no hierarchy) and 10 (motion: none).** Both are clearly present.
- **11 is a different flavour from the checklist.** There's no "Welcome back / Unlock / Seamless". The copy problem is internal engineering jargon, stale empty states and em dashes.
- **6 and 8 are mostly absent.** The text glyphs (✓ △ → ↗) do functional work. The grid overlay is faint and is the app's only motif.

## 4. Findings

**Severity:**

- **S1:** an accessibility failure on a core action or core signal. Fix whatever the direction.
- **S2:** hurts scanning or hierarchy, or reads as template.
- **S3:** polish.

### Cross-cutting

| ID | Sev | Finding | Evidence |
|---|---|---|---|
| F-01 | **S1** | **The primary action buttons fail contrast.** The build uses the rust *text* token `#e07a5c` as a button fill. The design README specified `#b8472f` for buttons, which login uses correctly (5.28:1). "Mark to apply" is the human-approval gate, and it appears 74 times on the page. | white/95 on `#e07a5c` = 2.81:1; ink on `#e07a5c` = 2.58:1. `potential-matches-client.tsx:683`, `to-apply-client.tsx:104`, `add-role-client.tsx:174`, `error.tsx:20`; compare `login-form.tsx:95` |
| F-02 | **S1** | **Readable text is mostly under 12 px.** Sizes in use: 8, 8.5, 9, 9.5, 10, 10.5 and 11 px. The smallest are the 8 px "FIT" label under every score and 9–9.5 px table headers and labels. | Section 2 table. `potential-matches-client.tsx:413`, `to-apply-client.tsx:84`, `applied-tracker-client.tsx:165,187,213`, `profile-client.tsx:116,121` |
| F-03 | **S1** | **The most-used text colour fails on the surfaces it's used on.** Faint `#6f828a` passes only on the bare page background. The owner email and zero counts use white at 30 % and 20 %. | Contrast table. 74 uses of `text-chart-faint` |
| F-04 | **S1** | **Source health is set in 8.5 px uppercase mono** in the Profile roster (92 instances). That contradicts "fail loud on source health", which the brief lists as a thing to keep. | `profile-client.tsx:191` |
| F-05 | S2 | **Mono is the main typeface.** IBM Plex Mono sets chips, labels, meta lines, buttons, links and nav counts: 64 % of the text on Matches. Mono should be for numbers and IDs only. | Live DOM: 834 of 1,294 elements |
| F-06 | S2 | **The headline serif is on the overused list.** Newsreader appears on every page title, the wordmark, drawer titles and empty states. It's also set with *wide* tracking (`tracking-wide`), the opposite of what you'd do with a display headline. | `globals.css:1`, `tailwind.config.ts:24`, every `<h1>` |
| F-07 | S2 | **Borders do all the structural work.** Cards, fit badges, chips, pills, buttons, inner evidence panels and every evidence row are boxed. On Profile, 130 boxes sit inside other boxes. Surfaces step in tone (page, panel, card), but borders are added on top anyway. | 821 bordered boxes on Matches; Profile nesting |
| F-08 | S2 | **Chip soup.** Every card carries six outlined mono chips (location, tier, feasibility, confidence, freshness, level) plus an outlined recommendation pill: seven of equal weight. The band colour repeats three times per card (badge, pill, band header), so it stops meaning anything. | `potential-matches-client.tsx:418–463, 370` |
| F-09 | S2 | **No hierarchy on Potential Matches.** All 74 cards are structurally identical. A 61 looks like an 88 apart from the digits. The rust button repeats on every card. 28 cards sit in "Apply now", so the band has stopped being special (see section 8). Nothing on the page says where to start. | S1; live counts |
| F-10 | S2 | **Pseudo-controls.** "sort · fit ↓" and "filter · all" are spans dressed as controls. Dismiss and Snooze are disabled buttons on every card and in the slide-over (148 inert buttons on the live page), with no explanation. | `potential-matches-client.tsx:244–245, 376–381, 566–571` |
| F-11 | S2 | **Symmetric stat strips.** Applied has 4 equal tiles plus a 6-segment funnel, all with 9.5 px uppercase labels. Profile has a 6-tile scan strip plus 4 coverage tiles. | `applied-tracker-client.tsx:153–200`, `profile-client.tsx:103–125` |
| F-12 | S2 | **Motion is absent, not excessive.** Both drawers snap open (the README specified a 220 ms slide). The only motion is Tailwind's default hover colour fade. There's no `prefers-reduced-motion` handling, and no deliberate "Mark to apply" moment. | No `animate`, keyframes or motion library in `web/` |
| F-13 | S2 | **The nav is implemented five times and has drifted.** Each page has its own sidebar. The Add a role page has **no Profile link**. Counts show only on the page you're on (the spec had live counts everywhere). Footer contents differ by page. This is charter rule 2 in the UI. | `SideNav`, `ToApplyNav`, `AppliedSideNav`, `ProfileNav`, and an inline nav in `add-role-client.tsx:54–63` |
| F-14 | S3 | **Copy.** Em dashes in drawer titles ("Mistral AI — Product Operations Manager") and empty states. Engineering jargon in subtitles: "current calibrated evaluator only", "one evaluator · three intake paths · no PDF upload", "Watchlist coverage · B-27", policy version strings in the Profile header, "Supabase Dashboard: Authentication > Users" on login. Stale empty states still mention the "evaluator-v3 migration" and "hybrid Claude v3". | `potential-matches-client.tsx:535, 706–709, 512`; `to-apply-client.tsx:139`; `profile-client.tsx:17`; `login-form.tsx:90–92` |
| F-15 | S3 | **The nautical world is barely there.** It's the name, a diamond and a 2.8 % grid. A navigator would recognise none of the chart's real visual language: soundings, depth tints, course lines, magenta navigation aids. | `potential-matches-client.tsx:82` (repeated on four pages) |

### By page

**Potential Matches** (S1; findings F-01, 02, 05, 07, 08, 09, 10, 12, 14). The page title is the only large thing. In the summary bar, the scan-reach line and the pseudo-chips compete with the band counts. Each card spends its width on seven pills and a 128 px action column with four controls, two of them dead. The expanded evidence block is a box inside a box. What works: the bands, the collapsed stretch band, the one-line summary, and freshness on every card.

**Role detail slide-over** (F-02, 07, 10, 12, 14 and **F-18**). F-18 (S2): no `role="dialog"`, no Escape to close, and no focus handling. The Applied drawer has `role="dialog"`, so the two drawers are inconsistent. Every evidence row and gap is its own bordered box. The fit badge sits halfway down beside the summary instead of leading. Under it, the evidence structure ("JD requirement → your evidence", strength, gaps with mitigations) is the best content in the app. Keep it exactly.

**To Apply** (F-01, 02). It's empty today. The card is the calmest in the app: plain-text meta, no chips. That proves the chips on Matches aren't needed. The fit badge here is always teal whatever the band, which is inconsistent with Matches.

**Applied** (F-02, 03, 11 and **F-17**). The stat strip and the funnel say the same thing twice. Zero counts are 1.9:1. F-17 (S3): in all 8 rows, 5 of the 10 columns (Next action, Due, Contact, Salary, Notes) show "—". The two columns the design meant to emphasise are empty, so the table reads as a field of dashes. There are also display bugs: "Sydney, , Australia" (empty location segment), and "10501" on Profile against "10,501" elsewhere. Row rules instead of row boxes is correct; keep that.

**Profile** (F-02, 04, 07, 11 and **F-16**). F-16 (S2): the **blended** coverage "54 %" is the page's 42 px hero and also a scan-strip tile. The tier-weighted figures, which are the actual gate (rule 13), sit smaller underneath, so the visual hierarchy contradicts our own rule. Long role-family text sits in bulleted panels inside panels. It's the densest page and the hardest to scan.

**Add a role** (F-01, 13, 14). The structure is reasonable: three intake modes, then a form. The submit button is 2.58:1, and the nav is missing Profile.

**Login** (F-14). It's the most correct page: its button passes contrast. The copy is engineering-facing.

## 5. What works and must survive any redesign

- Four separate signals (fit, feasibility, confidence, estimated level), never one blended score.
- "JD requirement → your evidence" with strength. Gaps paired with mitigations. Hard blockers in warn.
- Every pipeline move is an explicit click. Stage history is immutable and shown as such.
- The stretch band is collapsed by default. Freshness is on every card.
- No glow, no glass, no gradient washes. The palette is quiet.
- To Apply's plain-text meta row and Applied's ruled table rows already show the cleaner direction.

## 6. Tensions with `design-rules.md` (for Lasse to rule on)

- **Motion.** `design-rules.md` asks for staggered entry on every grid and a press scale on every button. The brief says "functional motion only". On a 74-card list that you scan daily, a 50 ms stagger adds about 3.7 s before the last card settles. My recommendation: the brief wins for this tool. One entry curve (`cubic-bezier(0.16, 1, 0.3, 1)`), drawers and row expand, one deliberate "Mark to apply" moment, and reduced motion honoured.
- **Fonts.** The faces `design-rules.md` names (Syne, Cabinet Grotesk, Clash) are fast becoming the 2026 "anti-AI" default themselves. The headline face should be chosen because it fits the chart world, not because it's on a list.

## 7. Fix-now candidates, independent of direction (not done: needs your go)

These are restyle-only, about one small PR, and would go through Cato. Recommended even if no redesign happens, because F-01 is an accessibility failure on the approval gate.

1. **Button fill:** use `#b8472f` (5.28:1 with white) for every primary button. This is the token the spec already defines.
2. **Faint text:** lift `#6f828a` to `#8597a0`, which reaches 5.25:1 even on cards. Replace `white/20` and `white/30` with that token.
3. **One shared nav component.** This fixes the missing Profile link and the count drift.
4. **Remove the sort and filter pseudo-chips.** Hide Dismiss and Snooze until they work, or label them "coming soon".

Per the brief's guardrail, these queue behind the ops work: B-35 (password recovery) and the stale `STATUS.md`.

## 8. Not design: observations for the backlog or ops

- **28 "Apply now" roles after the v4 backfill.** Earlier live digests surfaced a handful at most. If 28 is right, the band no longer works as "drop everything". If it isn't, it's a calibration issue. Worth a look in `live_calibration_notes.md` before designing hierarchy around the current counts.
- **Dismiss and Snooze aren't implemented.** That's product behaviour, a separate backlog item. The audit only covers how they're shown.
- The location label join ("Sydney, , Australia") is a small web data-formatting bug. It can be folded into the fix-now PR.

## 9. Direction options (Lasse picks)

| Option | Idea | Honest trade-off |
|---|---|---|
| **A. Refined dark chart** | Keep the night chart, fix the system. Tone-stepped surfaces with almost no borders. One distinctive display face, one workhorse UI face, mono only for numbers. Fit drawn as a bearing. Chips folded into one fit block. AA everywhere. | Lowest risk and quickest, but navy plus teal stays close to the genre we're escaping, so the taste has to come from execution rather than the concept. |
| **B. Light chart paper** | A day chart. Cream chart-paper ground, depth-tint blues stepping the surfaces, ink-black type. Magenta reserved for the one thing to act on, like a real navigation aid. Fit as an italic sounding. The pipeline drawn as a course line. Builds on the existing `Sextant Light.dc.html` palette. | The most distinctive and on-brand for Layline, and the one that reads as "designed" in an interview. It's also the biggest rebuild, a bright screen for evening use (dark could come later), and cream and magenta need careful contrast work. |
| **C. Dense operator log** | A logbook. One ruled row per role with columns for fit, feasibility, confidence, level and freshness. Expand inline. Keyboard first (j/k, a = mark to apply). Almost no decoration; the nautical world lives in the ruling and the numerals. | The fastest way to scan 95 roles a day and the most honest for a tool. The least visual impact in a 30-second demo, and the chart world nearly disappears. |

**My lean, for your decision:** B's world with C's density on Potential Matches. That means chart paper and magenta for the identity, and a ruled, scannable list for the daily job. If B feels too big a jump, A plus the section 7 fixes is a solid, cheaper floor.

## 10. Decision (1 Oct 2026)

Lasse reviewed rendered options (`docs/design/directions/`: A night chart, B day chart, C logbook, D chart v2, E logbook v2 in day and night). **The chosen direction is E, the logbook, in the day theme.** The night version was rejected because it lands back on checklist item 1, the default premium-dark look. Design brief: `docs/design/SEXTANT_LOGBOOK_BRIEF.md`. Lasse refines it in Claude Design. The Screening odds and Career value columns are product changes and are tracked as B-39.
