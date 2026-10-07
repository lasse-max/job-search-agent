# Brief for Otto · Sextant design check: lose the "AI-made" look

*Written 1 Oct 2026 by Otto (from the Movie Match session) at Lasse's request. For: Otto, in a job-search-agent session. Status: to start when Lasse says so. It must not jump the ops queue (section 6).*

---

## 1. Why this exists

On Movie Match, Lasse decided the app looked generically AI-made (dark background, one metallic accent, a "tasteful" serif, tracked mono caps, outlined pills, boxes everywhere). We are redesigning it with a real point of view. Lasse wants the same standard applied here: **Sextant should look designed by someone with taste and a reason, not generated.**

It is also a portfolio piece shown in interviews, so first impressions matter. But it is a daily tool for one user, so **clarity and speed of scanning come first**. This is not a brief to add flair.

## 2. Read first

1. `PM Projects/skills/design-inspiration/design-rules.md`: Lasse's own anti-AI design rules.
2. `PM Projects/Movie Match/movie-match/docs/design/PICTURE_PALACE_BRIEF.md`: the method used on Movie Match (a world, materials with one job each, one signature per moment, hard rules). Copy the **method, not the theme**. No cinema motifs here.
3. `docs/design/sextant/README.md` and the screenshots in `docs/design/sextant/screenshots/`: the current canonical design.
4. `web/app/globals.css`, `web/tailwind.config.ts` and the page components: what is actually built.
5. `docs/STATUS.md`, `docs/team-operating-brief.md`, `DECISIONS.md`: so design work fits this project's rules and timing.

## 3. The checklist: what reads as AI-made in 2026

Score each page (Potential Matches, role detail, To Apply, Applied, Profile, Add a role, login) against this list. Mark each item **present / partly / absent** and note where.

1. **The default "premium dark" recipe:** near-black or navy, one accent (gold or teal), a refined serif headline, mono uppercase tracked micro-labels.
2. **Boxes everywhere:** hairline-bordered rounded containers around every group, and cards inside cards.
3. **Chip soup:** many outlined pills of equal weight, so nothing leads.
4. **Symmetric stat strips:** rows of equal KPI tiles with tiny labels.
5. **Pseudo-controls:** text like "sort · fit ↓" styled as a chip instead of a real control.
6. **Icons in coloured circles**, emoji, decorative glyphs.
7. **Overused fonts:** Inter, Roboto, Geist, Space Grotesk, and as headline serif Fraunces, Instrument Serif, Newsreader.
8. **Gradient washes, glow and glassmorphism** used as decoration.
9. **No hierarchy:** everything the same size and weight; no single thing per screen that matters most.
10. **Motion:** either none, or random micro-animations everywhere.
11. **Generic copy:** "Welcome back", "Unlock", "Seamless", and em dashes.
12. **Accessibility misses** that often come with the look: 9 to 10 px mono labels, faint grey text under 4.5:1 contrast (check `#6f828a` and `#3d4c53` on `#0a141c`).

**My honest read from the screenshots (Otto to verify, not take as given):** Sextant hits 1, 2, 3, 4, 5, 7 and 12 clearly. The nautical idea is good but only shows in the name, a diamond and an optional grid. The structure underneath is a standard dark dashboard.

## 4. What "good" looks like here (principles, not a design)

- **A real world, used properly.** The world is the navigator's chart, which is already the Layline brand. Real nautical charts have their own visual language: chart paper, depth tints, soundings in small italic numerals, magenta for navigation aids, bearings and course lines. One possible bold move is a **light chart-paper theme**; a light variant already exists. Explore it as an option, do not decide it.
- **Hierarchy by size and tone, not by boxes.** Step surfaces in tone. Keep lines only where they carry meaning (a course line, a table rule).
- **One signature per screen.** For example, the fit score drawn as a sounding or bearing on Potential Matches. Everything else stays quiet.
- **Fewer chips.** Fold feasibility and confidence into the fit block. Location and tier can be plain text.
- **Type with a job.** One distinctive headline face, one workhorse UI face, mono only for numbers and IDs. Minimum 12 px for anything you need to read.
- **Functional motion only.** One entry curve, short durations, the drawer and row-expand transitions, and a deliberate "Mark to apply" moment, since that action is the human-approval gate. Respect reduced motion.
- **Keep what works:** four separate signals, never one blended score; evidence and gaps first-class; fail loud on source health; every pipeline move an explicit click.

## 5. Steps for Otto

1. **Audit.** Take a screenshot of each live page (job-search-agent-gilt-rho.vercel.app; Lasse logs in) and run the checklist. Write `docs/design/2026-10_design-audit.md`: findings by page, severity, screenshots referenced.
2. **Options, not a decision.** Sketch 2 or 3 genuinely different directions (for example: "refined dark chart", "light chart paper", "dense operator"). Give each an honest one-line trade-off. Lasse picks; Otto does not decide this alone.
3. **Design brief.** For the chosen direction, write a brief like Movie Match's (world, materials, type, signature moments, hard rules, the screen list to bring back). Lasse takes it to Claude Design or Figma.
4. **Build brief.** When the final design is back, write the builder brief in `docs/briefs/`: restyle only (`web/` components, styles and tokens), no data, scoring, auth or migration changes. Small commits, each with screenshots.
5. **Review.** Cato reviews against the design brief, and checks for regressions: the four signals still distinct, gates intact, nothing auto-advancing, accessibility floor met.
6. **Docs.** Update `STATUS.md` and the Sextant design README at the end.

## 6. Guardrails

- **Timing.** Ops comes first. The post-merge checks, the refreshed preflight and the 14-day backfill, B-35 (password recovery) and the stale `STATUS.md` all come before this. The audit (step 1) can run anytime because it is read-only. Steps 3 to 5 start only when Lasse says so.
- **Scope.** Visual layer only. Any idea that changes product behaviour (new fields, new pages, changes to what gets scored) goes to the backlog as a separate item.
- **Rules of this repo apply.** Builder and reviewer are different models. Briefs live in `docs/briefs/`. Owner-only actions stay with Lasse.
- **Consult before changing scope, order or rules.** Lasse's standing preference.
