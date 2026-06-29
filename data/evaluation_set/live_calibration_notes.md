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
