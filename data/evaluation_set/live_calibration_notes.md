# Live calibration notes

Running log of owner disagreements with the live evaluator, captured from real digests. Feeds the next tuning loop (B-15 stretch-band + apply/consider calibration). Each note: role · evaluator call · owner call · why.

## 2026-06-27 (first live digest)

- **Databricks — Manager, Sales Development** · evaluator **apply_now** (fit 74, Tier 1) · owner: **skip**. Sales-team (SDR) leadership, not an S&O target family. Evaluator over-weighting the Tier-1 brand + "Manager."
- **Databricks — Solutions Architect (Benelux Hunter, Pre-sales)** · evaluator **apply_now** (fit 70, Tier 1) · owner: **skip**. Technical pre-sales — same family as the Celonis Value Engineers already labeled skip.

**Pattern:** the `apply_now` band is inflated by **Tier-1 brand on sales / pre-sales-flavored roles**. Likely fixes for the tuning loop: down-rank pure Sales-Development and Solutions-Architect/pre-sales titles regardless of brand; reduce the Tier-1 brand lift on non-target functions. Confirmed-good this cycle: Harvey GTM S&O (apply_now), Sierra GTM Operations (consider).

## 2026-06-29 (Mon digest, 25/48)

Owner direction: **no brand-specific logic** (don't special-case Databricks); fix the *general* failure modes.

1. **🔴 Band/fit must be strict & monotonic (→ DECISIONS #61).** A `consider`/Tier-1/warm-path override floated a weaker role above stronger ones: Databricks Technical PM (fit 73) was `apply_now` while Palantir Deployment Strategist (fit 81) was only `consider`. Fix: band = strict function of fit (80+ apply_now · 70–79 consider · 60–69 stretch · <60 skip); warm-path/tier/brand feed the fit *score*, never a post-hoc band jump. Blockers/infeasible can only push down.
2. **Function gate fooled by keywords ("GTM"/"Operations").** Two clear false-positive `consider`s: **Anthropic "Recruiter, G&A or GTM"** (Talent/HR — off-function, matched "GTM") and **Palantir "Site Reliability Operations Analyst"** (SRE/eng + analyst-level — matched "Operations"). The gate must weight the core function noun (Recruiter, SRE, Solutions Architect, Technical PM) over incidental keywords. Same failure class as the original firehose, milder.
3. **Required credentials the candidate lacks don't down-rank.** Databricks Technical PM *requires* PMP + intermediate Databricks platform cert within 6 months (stated requirements) — evaluator waved them off as "obtainable" and kept apply_now. Extend the hard-requirement handling beyond CS-degree/production-coding: a required cert/platform-fluency the candidate lacks should reduce fit (or block if clearly central).
4. **Multi-location dedup (B-02).** Stretch band = the *same* Databricks "AWS Cloud Partner Solutions Architect — EMEA" listed 3× (Paris / London+Paris / Berlin+Munich+Paris). Group one role, list its locations.

Genuinely on-target this cycle: Palantir Deployment Strategist — Amsterdam (81) & Madrid (75). (Owner to confirm appetite for Palantir commercial roles generally.)

## 2026-06-30 (Tue digest, 279 new — strict bands LIVE)

**Wins:** strict monotonic bands confirmed working (consider all 70–79, stretch all 60–69, no conflicts/inversions). Consider band clean & trustworthy — Airbnb Sr Growth & Ops (79), Airwallex Ops Strategy (78), Sierra Strategist ×2 (72), Checkout Process Architect (70); no Recruiter/SRE false-positives. Scan-reach stat live ("6,871 postings across 31 companies"). Daily cron fired on schedule (6:31am).

**Flags (feed B-15 + encode 2 prefs):**
1. **Encode the defense-decline (priority — explicit owner instruction ignored).** "Palantir — Deployment Strategist — AUS Government" (stretch 68) surfaced; owner declined Palantir defense/government (LNP-142). Add a rule: government/defense/clearance roles → skip (or block), not stretch.
2. **Pre-sales / "Value Partner" head-function should skip.** "Celonis — Principal Client Value Partner" (62) = value-engineering pre-sales (the family already labeled skip), leaked to stretch.
3. **Stretch band still noisy (expected, B-15 untuned):** Logistics Standards, Risk Operations, Proposals & Assurance, Integration Manager — adjacent-ops/skips.
4. **Language-variant dedup (extend B-02):** Sierra Strategist French + Spanish = one role, two languages — dedup catches city variants but not language variants.
5. **Watch single-company over-representation:** Checkout.com = ~6 of ~14 surfaced this cycle.

## 2026-07-04 (Sat digest — first calibration-floor firing)

**Win:** Anthropic — Partnership Strategy & Operations Lead, International (fit 82, London, Tier 1) → clean, correct `apply_now`. BFL now in scan count ("6,901 across 32 companies").

**🔴 Fit ≠ band for gated roles — the calibration floor exposed it.** Only 1 role surfaced, so the "Top open roles by fit" floor fired with 5 roles all at **fit 87** — *higher than the fit-82 apply_now* — yet all "below bar": Airbnb Product Manager EMEA (87, native PM, conf 68%), Block Partner Marketing (87, marketing), HelloFresh Senior Director of Product (87, over-level PM, Warsaw/Toronto off-location), + 2 Block Partnerships Managers (87). Under strict bands fit≥80 should be apply_now — impossible unless fit and band have decoupled. Cause: the **function/location/level gate skips a role but does NOT lower its fit score**, so off-function/off-location roles keep high LLM fit (87) while being gated to skip; the floor ranks by raw fit and surfaces them.
- **Fix:** gate penalties (off-function, off-location, over-level, required-credential, language) must **reduce the fit score itself** so fit is the true single ranking and never disagrees with band (a native PM should score ~40, not 87). Then the floor shows genuine near-misses.
- Secondary: floor should refresh stale pre-recalibration cached scores and/or draw only from gate-eligible roles.

**🟠 Use salary/comp as a seniority signal.** The Anthropic apply_now (fit 82) self-described as "aligned to L4–L5," but that was read from JD scope words, not the posted comp band. Owner reads the salary as ~L6 — i.e. a notch above the target ceiling. The evaluator ignores stated compensation for leveling. Fix: when a posting includes a pay band, infer level from it; a band materially above the L4–L5 target → over-level down-rank (folds into item 0 — level penalty reduces fit). NB: a senior-IC "Lead" that's L6 is a legitimate stretch-up, not a hard skip; the ceiling rule targets Head-of/Director/VP function-heads.

**Why off-function roles score high (root cause, for the fix):** fit rewards experience/keyword overlap ("Partner", "Strategic", commercial/GTM/stakeholder tokens) with no function-mismatch penalty — a Partner *Marketing* Manager maps onto the owner's partner-ops/commercial background and scores ~87, while the gate skips it separately. Fit must incorporate the mismatch so the number itself is low.
