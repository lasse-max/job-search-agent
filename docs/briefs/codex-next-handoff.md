# Codex Handoff — current queue (2026-07-12)

Ordered. Effort dial noted per item (owner default is **high**; deviations flagged).

---

## 1. Housekeeping commit — **medium**

- **Commit the HelloFresh opt-out** — `config/candidate_profile.yaml`, `employer_opt_outs.HelloFresh` (owner opted out 2026-07-12; does not rate the product). Same treatment as Palantir: config-level employer opt-out, **not** brand logic in the scorer, trivially reversible.
- **Commit the backlog additions** — `docs/BACKLOG.md` B-30 and B-31.

## 2. 🐛 Profile watchlist regression — **medium**

The coverage instrumentation (`708f398`) replaced the full per-tier company list with **only the dark companies**. The owner can no longer see **which companies are actually being scanned** — which is half the point of the page. The previous version (full list per tier, each with `enabled` / `manual off` + coverage state) was better.

**Restore the full per-tier company list with each company's status, AND keep the coverage numbers.** Both, not either. Coverage %, tier breakdown, dark-company reasons *and* the complete roster.

## 3. ✨ B-30 — Manual job entry ("Add a role") — **high**

The owner needs to track roles the agent didn't catch: referrals, LinkedIn finds, and above all the **61 dark companies (B-27)**. **The backend already exists and is unused:** `app/services/manual_intake.py` with the `add-url` and `add-text` CLI commands — both fetch/parse a JD and run it through the **same evaluator and the same gates**. This is a **missing front door, not a new feature.**

### The fallback ladder (owner decision 2026-07-12)

1. **Paste a URL** *(primary)* → fetch → parse → evaluate → lands in the pipeline with a real fit score, alignments, gaps, and estimated level. Works for most ATS.
2. **Paste JD text** *(the workhorse fallback)* → for JS-heavy / login-walled / custom career sites (**Google, Apple, Amazon**) that cannot be fetched. **Critically: the owner still gets the FULL evaluation** — the text is all the evaluator actually needs. The cost of a dark company is *one extra copy-paste*, not the loss of scoring. Make this path obvious and first-class in the UI, not a hidden degraded mode.
3. **Manual line + note** *(last resort)* → company / title / link / note, **unscored and clearly marked "not evaluated."** Only when the JD text can't be obtained at all. The owner must never be blocked.

**Explicitly NOT doing: PDF upload.** Strictly worse than pasting text (save → upload → parse → extract, vs. Cmd+A/Cmd+C), more machinery, more failure modes, same destination.

### Requirements
- Flag manual entries `source_type: "manual"`.
- Where the company is **off-watchlist**, offer to propose it for the watchlist.
- Allow the entry to drop straight into **Potential Matches**, **To Apply**, or **Applied** (a referral may already be applied to).
- Reuse the existing gates/evaluator — no parallel scoring path.
- Owner-gated writes via the existing RPC pattern; keep the calibrated-read rules.

## 4. Coverage expansion (B-27) — **medium** — see `docs/briefs/coverage-expansion.md`

Full brief already written. **Do not enable new sources without the owner** — each new feed multiplies postings → LLM spend against the monthly cap. Build + audit now; the owner enables in batches of 3–5 and watches volume/spend/runtime.

---

## In review with Cato
- `3403c06` — quiet-day heartbeat (pure-alert model retained; zero repeated roles; never silent).

## Standing rules
- **Migrations:** Codex writes them; the **owner applies them by hand**. Never write to the live database.
- **Blocker-class findings (🔴/🟠)** stay on the backlog until FIXED or FORMALLY ACCEPTED in `DECISIONS.md`. They never age out because a newer finding arrived. *(Adopted after B-29 escaped twice.)*
- **A rule implemented in two places will drift.** Version constants, freshness policy — derive from one source, with a test that fails when they disagree.
- **Report item count + ETA before any long-running job**, not just projected spend. (Runtime, not cost, is what killed the v4 backfill.)
