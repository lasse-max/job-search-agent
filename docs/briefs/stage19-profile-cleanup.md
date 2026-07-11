# Codex Brief — Stage 1.9 Profile Clean-up (single pass, version bump)

**Priority: do this BEFORE any re-score/backfill.** The Postgres calibrated view now requires `hybrid_claude_v3`, so the app is **empty** until a backfill runs. Do not spend a re-eval cycle at v3 — the profile is known-wrong. Land this clean-up, bump the evaluator version (**→ v4**), then run **one** backfill so the corpus is re-scored **once**, against a correct profile. Two full re-scores would burn the `MONTHLY_MODEL_SPEND_CAP_USD` ($15) for nothing.

**Owner-approved in conversation 2026-07-11.** This is the Stage 1.9 "Profile clean-up" workstream (`ROADMAP.md`).

---

## 1. 🔴 Add a tools/skills section — the biggest false-gap source in the system

`config/candidate_profile.yaml` currently has **no technical-skills section at all**. The only technical statement is `honest_gaps: "Python basic and actively learning"`. Consequence: the evaluator correctly reports that the profile doesn't mention these tools, and so invents the **same false gap on nearly every role** — *"No explicit SQL and advanced Excel proficiency confirmed"* (Airbnb), *"No explicit Salesforce.com or CRM administration experience documented"* (OpenAI), *"specific tool proficiency not detailed in candidate profile"* (Airwallex), *"No explicit evidence of SQL or CRM platform experience"* (Sierra). This has been suppressing fit scores across the entire corpus.

Add a `tools_and_skills` block (owner-stated, honest — do not inflate):

```yaml
tools_and_skills:
  SQL: "proficient — joins, GROUP BY, subqueries/CTEs, window functions; queries BigQuery directly to pull and shape own data"
  Salesforce: "admin — managed territory budgets; partnered with engineering on feature requests"
  Looker: "builds dashboards"
  Tableau: "yes"
  Excel: "advanced"
  Google Sheets: "advanced"
  BigQuery: "working — writes queries, pulls and shapes own data"
  Python: "basic, actively learning (data-analysis / pandas track)"
  AI and agentic tooling: "designs, specs and directs LLM coding agents to build production systems; owns evaluation methodology, benchmarking and calibration"
```

- **Wire it into the evaluator's evidence base** so `alignments` can cite it and `gaps` stop inventing it.
- **The Salesforce line is the highest-value single fix.** It is the most-cited gap in the entire digest, and it is false — the owner is an admin who managed territories. Note the OpenAI ANZ JD explicitly asks for *"building territories, comp plans, setting quotas… using Salesforce.com"* — that must now read as an **alignment**, not a gap.
- **Update `honest_gaps`:** keep Python honest ("basic, learning") but remove any implication of general technical illiteracy. Do NOT overclaim Python — a stated *requirement* for advanced/production Python must still hard-disqualify.

## 2. Promote Partner Operations to a primary role family

The profile already lists `core_strengths: "Partner operations and vendor-team leadership"` and flagship evidence of **96 partners in five months** and **120+ partners across regions** — yet **Partner Operations is not a target family**. The agent has been systematically not looking for one of the owner's strongest areas.

- Add **"Partner Operations / Partner Strategy & Operations"** to `primary_role_families`.
- Add matching `role_family_patterns.primary` regexes (e.g. `\bpartner (?:operations|ops|strateg\w*)\b`, `\bchannel (?:operations|ops)\b`, `\bpartner field operations\b`, `\bpartnerships? (?:operations|strateg\w*)\b`) — **without** matching pure BD/partnerships *sales* roles.

## 3. Add Program / Project Management as an **approved stretch** (not primary)

A legitimate entry path into the target companies, and a clean map to the owner's transformation / rollout / UAT background — but generic PM/TPM would flood the digest with engineering-delivery roles.

- Add to `approved_stretch_families`: **"Program / Project Management (Technical Program Manager, Strategic Program Manager) where the role owns business or strategic programs — NOT pure engineering-delivery PM."**
- Gate it on scope: business/strategic program ownership, cross-functional execution, transformation. Exclude pure SDLC/engineering-delivery TPM.

## 4. Commercial Operations → Revenue Operations translation

Owner question: *"is my commercial operations classified as revenue operations externally?"* **Answer: overlapping skills, different domain — and the mismatch is costing him.**

- **RevOps** (SaaS/tech convention) = the *sales* engine: pipeline, forecasting, CRM, territory/quota/comp design, funnel metrics; usually under a CRO.
- **Commercial Operations** (owner's Google Devices world) = the operational machinery of a *product/channel* business: partner/channel ops, order-to-cash, claims and deductions, pricing execution, sell-through.

Same muscles, different arena — so a recruiter scanning for "quota / pipeline / forecast / Salesforce" won't find them, **even though the owner has genuinely revenue-flavoured wins** (`"recovered tens of millions in revenue"`, `"reduced aged deductions backlog by 95%"` — that is revenue-leakage recovery, deeply RevOps; plus Salesforce admin + territory budgets).

**Action:** add an explicit mapping note to `positioning` / the evaluator prompt so the evaluator understands the owner's commercial-ops background **maps onto RevOps requirements** (revenue recovery, territory management, CRM administration, forecasting/reporting cadences, pricing execution) rather than treating "revenue operations" as an unmet requirement. This is a translation problem, not a capability gap.

## 5. Narrow the location allowlist (owner decision)

**Keep (14):** London · Berlin · Munich · **Hamburg** · Amsterdam · Paris · **Copenhagen** · Zurich · **Lisbon** · Singapore · Sydney · Melbourne · **Perth** · **Brisbane**

**Drop (5):** Stockholm · Madrid · Milan · Brussels · Vienna — **Spain out entirely** (Madrid-without-Barcelona was an arbitrary inherited assumption; owner is not pursuing Spain).

**Unchanged:** Dublin = Tier-1 only · United States = high-friction / not authorized. Update **both** `allowlist` **and** the `pre_evaluation_filter.allowed_location_patterns` regex (the regex is a hard pre-eval gate — updating only the allowlist would leave roles silently dropped).

---

## Version bump + re-score (do this once)

Bump the evaluator version (**→ `hybrid_claude_v4`**) so the corrected profile actually takes effect — **cached evaluations are not invalidated by a profile change**, so without a bump these fixes would not reach the existing corpus. Then run **one** backfill/re-score.

**Check the spend ledger first.** The v3 sweep already consumed budget; confirm a full v4 re-score fits under `MONTHLY_MODEL_SPEND_CAP_USD` before kicking it off, and report the projected cost.

Re-run cached + live benchmarks (expect fit scores to **rise** — false gaps removed — so re-verify the bands still hold and precision doesn't collapse). Update `DECISIONS.md`. Push, back to Cato.
