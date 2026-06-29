# Codex — CALIBRATION LOOP (Stage 1.5) — from owner review of the 2026-06-29 digest

Owner direction: **no brand-specific logic** (do NOT special-case Databricks). Fix the general failure modes. Details in `data/evaluation_set/live_calibration_notes.md` (2026-06-29).

1. **🔴 Strict, monotonic band = function of fit only (DECISIONS #61).** Remove the post-hoc recommendation overrides (e.g. "Tier-1 + warm path → bump to apply_now") that let a lower-fit role outrank a higher-fit one (Databricks fit 73 was apply_now while Palantir fit 81 was consider). New rule, hard thresholds on the final code-computed fit:
   - **fit ≥ 80 → apply_now · 70–79 → consider · 60–69 → stretch · <60 → skip**
   - Hard blockers / infeasible may override **downward only** (→ blocked/skip), never upward.
   - Warm path, company tier, and brand remain **inputs to the fit score** (they raise/lower the number via the dimensions), not separate band jumps. Net: band is a dumb, strict, interpretable function of fit; no two roles ever conflict.
   - Re-run BOTH benchmarks after this — the threshold change moves the curated/live mappings; confirm recall ≥95% / precision still holds, and re-tune dimension weights (not the thresholds) if needed.
2. **Function gate weights the core role noun over incidental keywords.** Two live false-positives slipped in via "GTM"/"Operations": **Recruiter (Talent/HR)** and **Site Reliability / SRE (engineering, analyst-level)**. The gate must classify on the head function (Recruiter, SRE, Solutions Architect, Technical PM, …) and skip those families regardless of a "GTM"/"Operations"/"Strategy" keyword elsewhere in the title.
3. **Required-credential down-ranking.** Extend hard-requirement handling beyond CS-degree/production-coding: a JD that **requires** a credential the candidate lacks (e.g. PMP, a platform certification, intermediate platform fluency) should reduce fit materially (gap-manageability/penalty), and block only if that credential is central. (The Databricks Technical PM required PMP + Databricks cert within 6 months and still got apply_now.)
4. **Multi-location dedup (B-02) — pull forward.** The same role across city variants (e.g. one Solutions Architect listed 3× for Paris / London / Berlin) must surface **once** with all locations listed, not as duplicate cards.
5. **Confirm cadence stays once daily** (`0 6 * * *`) — already set in `558a6c5`; no change, just verify it didn't regress.

Re-run cached + live benchmarks, push, back to Cato. This is the Stage-1.5 search-refinement work (ROADMAP).

---

# Codex — FIX LOOP 6 (email guard too strict — blocks every live run) — EMAIL-BLOCKING

Symptom: every scheduled run = `failure`, `Digest uses fallback evaluator output; refusing email delivery`, `notification_status=failed`, no email — even though the run takes **18 min** (so Claude DID score the bulk of the ~93 roles; the evaluator is working). Root cause: the **email-delivery guard is all-or-nothing** — `uses_fallback_evaluator(rows)` refuses the entire digest if **any** surfaced row is fallback-quality. On a live run with ~100 roles / hundreds of Claude calls, ≥1 role always falls back (transient 429/529/timeout, or a response that won't coerce), so the email is blocked **permanently**. This is the inverse of the firehose: now too conservative to ever ship. Fix Loop 5 relaxed the per-source role *drop* but the email guard still blocks on any single fallback row.

1. **Exclude fallback-quality rows from the emailed digest instead of blocking the whole email.** Any role without a validated LLM evaluation is withheld from the email + logged (extend the Fix Loop 5 drop to ALL fallback causes: provider error, cost-cap halt, un-coercible output — not just validation crashes).
2. **Always deliver — never block to zero, single 25 cap in both modes (owner decision DECISIONS #59).**
   - **One cap, 25 (config; hard max 50 per #53), applied in BOTH modes** — NO special small/"5" cap. Owner: never miss a good role to an arbitrary floor.
   - **Normal:** ≥1 validly-LLM-scored role → send valid roles ranked by fit, up to 25 (drop fallback ones + count them). >25 qualifying → top 25 + an overflow line "➕ N more — view full list" pointing to the full local digest / `job-agent review list` / CSV exports (eventual home: Stage 2 Opportunity Inbox).
   - **Degraded (0 valid LLM evaluations — wholesale fallback / cost-cap / provider down):** do NOT block — send the same up-to-25 digest, stamped loudly (subject + top banner: "⚠️ DEGRADED — unvalidated stub scores, ranking not trustworthy"). Proof-of-life + calibration signal; can't firehose (≤25 + labeled).
   Surface the dropped/fallback count + degraded state in the failures section (fail-loud preserved). Supersedes Fix Loop 5 #3's hard block-on-wholesale-fallback — firehose protection is now the 25 cap + loud degraded label, never a zero-email block.
3. **Add transient-error resilience** on provider calls: bounded retry + backoff on 429/529/timeout (tenacity is already a dep) so fewer roles fall back on big runs.
4. **Confirm the digest cap (#53) applies to the email** — `notification_roles=93` is far over the 25/50 cap. Apply/consider capped to N; remainder summarized.
5. **Verify it's not the cost-cap ledger.** The 18-min runtime suggests the evaluator ran (not a wholesale cost-cap halt), but confirm the cache-persisted `MONTHLY_MODEL_SPEND_CAP_USD` ledger isn't near-exhausted and forcing fallbacks; if it is, that's a second cause to address (raise/scope the cap, or reset stale cache ledger).
6. **Don't let exit-code conflate "a flaky source" with "run failed."** Decide (Otto note): a single `degraded` source (e.g. Atlassian fetched 0) should surface in the digest, not necessarily turn the whole scheduled run red every time. At minimum, a *delivered email with healthy evaluation* should not be reported as a total failure.
7. **Regression tests (update, don't just add):** (a) mixed valid + fallback rows → email SENDS valid rows only (≤25), fallback count flagged; (b) **all-fallback → email SENDS the up-to-25, loudly-labeled DEGRADED digest** (no firehose: ≤25 cap + label); (c) >25 qualifying → exactly 25 shown + overflow pointer. **This flips the `55e76d7` `FailAllRolesProvider` test**, which currently asserts all-fail *blocks* — update it to assert the degraded labeled send instead. Reconcile DECISIONS #58/#59 so the design log isn't self-contradictory.

Note: the ~93 "new" backlog is a snowball from repeated failed runs not advancing notified-state — it shrinks to normal once one run delivers. Ship-completing; justified despite freeze. Re-run, push, back to Cato.

---

# Codex — FIX LOOP 5 (live run: LLM output validation crash) — EMAIL-BLOCKING

Secrets are now correct (Claude runs live). New blocker from the first real scheduled run: a live Claude response returned a **list field as a JSON-encoded string**, so `LLMEvaluationOutput.model_validate` raised and the role fell back → loud guard blocked the whole email. Exact error (Databricks): `ValidationError … alignments — Input should be a valid list … input_value='[\n {\n "job_require…'`. The cached benchmark never caught this (cache holds clean outputs); only live calls produce the format wobble.

1. **Coerce stringified-JSON list fields before validation.** `LLMEvaluationOutput` (llm_evaluator.py:52) already has a `field_validator("hard_blockers", mode="before")` (line 67). Add the same `mode="before"` coercion for **`alignments`, `gaps`, `uncertainties`** (and verify `hard_blockers`): if the incoming value is a `str`, `json.loads` it first and use the resulting list. Handles the exact failure above.
2. **Retry once, then degrade per-role — do NOT nuke the whole digest.** If a role still fails validation after coercion + one re-request, drop/flag *that one role* only. A single malformed response must not mark the entire digest as fallback.
3. **Scope the loud-fallback guard correctly.** Block email only when the evaluator is wholesale non-functional (no key / provider down / all roles failing) — NOT when one role wobbled. Distinguish "evaluator broken" (block — the firehose protection) from "one role dropped" (send the rest). Today one bad response permanently blocks the digest.
4. **Regression tests from the real failure:** (a) an LLM response with `alignments` as a JSON string parses cleanly; (b) a digest with 1 dropped malformed role among many valid ones still sends.
5. **Backlog (now doubly relevant):** log *why* a role fell back (provider error vs malformed output vs no key) — the current log can't distinguish, which cost a debugging round.

Re-run cached benchmark + a live-shaped test, push, back to Cato. This is ship-completing (makes the core email work), not gold-plating — justified despite the fix-freeze.

---

# Codex — FIX LOOP 4 (Cato 🟠 on `34ebc3c`: hard-requirement blocker under-fires) — EMAIL-BLOCKING

Cato's full review confirmed 34ebc3c is a genuine mechanism fix (no overfit), but found the blocker now **under-fires on common phrasing** — the inverse of the earlier over-block. Must close before owner sign-off to re-enable email.

1. **[🟠 required] Broaden must-have detection + make technical-depth disqualifiers self-enforcing.**
   - `must_have_context_patterns` currently matches only `\brequired\b`. Broaden to `require(s|d|ment)?`, `mandatory`, `must`, `need(ed)? to`.
   - More robust: enforce **technical-depth disqualifiers (production coding / advanced programming / deep ML as a central duty) regardless of must-have phrasing** — per PRD §5.3 it's a true blocker on *centrality*, not on the word "required." `_llm_hard_blocker_is_enforceable` currently drops the blocker at the must-have gate *before* the `_technical_depth_requirement` override runs (override is partially dead on the LLM path) — fix the ordering so the technical-depth override can enforce.
   - **Add the complementary regression test** (mirror of the degree test): a stretch-family role whose text *requires* production software development / advanced Python / deep ML still resolves to `blocked`. Use varied phrasings (requires / mandatory / must).
2. **[🟡 confirm] Justify or soften the `role_family_fit` floor of 82.** Confirm a primary-family title floored to 82 isn't (a) re-admitting weak primary-titled roles, or (b) doing the benchmark's work — i.e. that LNP-090's apply_now reflects genuine fit, not just the floor. If it's masking, soften to a prior rather than a hard floor.
3. **[reconcile] Confirm the carry-over fixes actually landed.** Cato lists the silent-fallback footgun + cost-cap/volume math as still-standing. Point to the tests proving `a36ae0c`'s loud-fallback (no email on fallback eval) and corrected cost math are in place; if they regressed or were partial, fix.
4. **[🟡 widen] Grow the labeled positive set.** Sample more known-good S&O/primary-family roles across companies into the precision set for Lasse to label, reducing one-role metric swing (currently 9/9, 9/10 on ~10 positives).
5. **[process] Confirm hosted GitHub Actions is green** on the latest commit (owner to check the Actions tab — it's been unverifiable from the build env every loop).

Re-run cached benchmark + the new blocker test, push, **back to Cato**.

**Owner decision — monitored soft-launch.** Email re-enable gate = **🟠 closed + carry-overs confirmed + Cato clears + owner sign-off.** Widening the positive label set (item 4) is **parallel, not blocking** — done from roles Lasse flags in live digests. Soft-launch relies on: clean apply/consider bands, the labeled "scrutinize" stretch section as the owner's calibration radar, the hard 25/50 cap, and loud-fallback.

---

# Codex — FIX LOOP 3 (Cato 🟠 on `34ebc3c`: metric ignores stretch, but the digest sends it)

Owner decision: **keep full stretch cards in the email** (used as a calibration-monitoring surface). So the metric must now reflect what's delivered — close the mismatch by *measuring* stretch, not by hiding or dropping it.

1. **Fix the precision report to match delivery.** Report TWO precision numbers in `live_noise_precision_report`:
   - **Apply/Consider precision** (the calibrated bands) — keep gating this **≥80%** (currently 9/9).
   - **All-surfaced precision INCLUDING stretch** (= what the email actually shows as full cards: apply_now + consider + stretch). Compute and display it; **report-only, not gated** for the MVP. It will read low (~11/20 ≈ 55%) because the stretch band is still noisy — that's the intended visibility, not a failure. This directly resolves Cato's flag: the metric can no longer claim "no firehose" while ignoring 9 skip→stretch roles.
   - Keep live Apply/Consider **recall ≥90%** gated.
2. **Label the stretch section in the digest** as lower-confidence, e.g. "Stretch / reach — calibration in progress, scrutinize." So its noise is explicit to the reader.
3. **Backlog (next calibration target, not this loop):** the stretch band is noisy — 9 skip→stretch incl. **LNP-142 Palantir (defense — owner declined; should down-rank to skip)**, LNP-112 Talent Acquisition, LNP-062 associate pricing. Tune the stretch band + encode the defense-preference down-rank, informed by what the owner flags from live emails. Also grow the labeled positive set over time (currently thin at 10 — Cato 🟡).

After 1–2: re-run cached benchmark, push, **back to Cato for re-review**. Email re-enable = apply/consider gates green + stretch shown-and-measured + owner sign-off.

---

# Codex — FIX LOOP 2 (calibration regression on `5f9661e`)

The real evaluator ran but is now **too conservative** — the green "precision 6/6" hides a recall miss on the live set. From `live_noise_precision_report.md`: of ~10 roles labeled apply/consider, only 6 surfaced (~60% recall). Fix the **mechanism**, then re-benchmark; do NOT hand-tune to pass individual rows.

**Bug 1 — `apply_now` looks unreachable.** Zero roles got `apply_now` in the whole 150, even at fit 82. **LNP-090** (Airwallex Sr Mgr, Revenue Strategy & Operations, fit **82**, owner-labeled `apply_now`) was recommended **stretch**. Check the post-LLM band logic: a fit ≥80, non-blocked, Tier-1/2 role must reach `apply_now` (PRD §5.5). Confirm the band thresholds and tier read-through aren't demoting strong S&O roles to stretch (also **LNP-119**, fit 77, consider → stretch).

**Bug 2 — hard-blocker over-firing.** **LNP-020** (Pigment AI Deployment Strategist, London, owner-labeled consider) was **blocked** at fit 69; dozens of `skip` roles are marked `blocked` broadly. Likely the `disqualifying_hard_requirement` (#51) catching non-must-have "Python/technical" language in Deployment-Strategist/Applied JDs. Enforce: it fires **only** on must-have / required / minimum-qualification language (never "preferred / a plus / familiarity / experience with"). A clean Deployment Strategist in an allowed location must not be blocked.

**Bug 3 — benchmark reports precision without recall (same false-confidence pattern as #48).** Add **live-set recall** to `live_noise_precision_report`: of roles labeled apply/consider, how many the evaluator surfaced as apply/consider. Gate on it. Precision alone cannot pass.

**Acceptance for this loop:**
- `apply_now` is reachable; LNP-090 surfaces as `apply_now` (or at minimum apply/consider — surfaced).
- LNP-020 is no longer `blocked` (surfaces as consider/stretch); broad skip→blocked over-firing reduced.
- Report **both** live precision **and** live recall (evaluator named). Targets: live apply/consider **recall ≥90%** (≤1 miss of the ~10) AND **precision ≥80%**, recall ≥95% held on curated.
- Defensible non-bugs (don't force): LNP-061 (consider→stretch, fit 58), LNP-111 (stretch→skip, fit 48) — leave to the model unless the mechanism fix naturally moves them.
- Re-run cached benchmark, push. Then to Cato.

---

# Codex — next instruction (ordered) [prior loop, mostly shipped]

> **STATE (live):** Steps 1–4 + 6 shipped in `a36ae0c` (loud fallback, cost math, gate leaks, location filter, hard-requirement blocker). Both label sets are now **labeled by Otto** (gate-recall `live_noise_labels.yaml`: 146 skip / 4 surfaced; precision `live_noise_precision_set.yaml`: 138 skip / 1 apply_now / 9 consider / 2 stretch) — **commit them**. REMAINING: add seniority ceiling **#52**; actually run Claude + populate `llm_cache`; switch `benchmark` to the cached LLM provider; calibrate to recall ≥95% + precision ≥80%. The LLM machinery exists (`c796a40`) but has never been run — that's the gap.
>
> **New rule to encode — DECISIONS #53 (hard digest cap, defense-in-depth):** Cap total surfaced roles in any email digest. Config-driven `digest_max_roles` default **25**, absolute max **50**. Render the top N by rank (apply_now → consider → stretch); collapse the remainder to a count. **Must be loud, not silent:** the digest states "showing 25 of N surfaced," and if N exceeds an anomaly threshold (e.g. >2× the cap) it raises a visible health warning that the evaluator is over-surfacing — never quietly truncate (a silent cap could mask a firehose recurrence). Ships independent of LLM calibration — it's the structural backstop so the 1,064-role email can't physically recur.
>
> **New rule to encode — DECISIONS #52 (seniority ceiling):** target band L4–L5 (Manager / Senior Manager / Lead / Senior IC). "Head of / Director / VP / C-suite" at an established company → over-leveled → `skip` even when function matches (skip on level, don't mislabel function). Exception: small startups where "Head of" ≈ L4–L5 scope. Encode in `candidate_profile.yaml` + `scope_seniority` logic + prompt.


Full detail in `docs/briefs/llm-evaluator-slice.md`. Build to PRD/ROADMAP, commit small, pause for Cato re-review, log ADRs in DECISIONS.md. **Do NOT re-enable live email.** Do NOT start Stage 2/3.

Do these in order:

**1. Loud fallback (required).** If `ANTHROPIC_API_KEY` is missing/expired/over-cap, `evaluate_role` must NOT silently use the deterministic stub. Flag fallback-quality runs and **refuse to compose/send an email digest** built from the fallback. Local files may render but must be marked "fallback evaluator — not validated."

**2. Cost-cap math.** Fix the per-eval estimate to real Haiku pricing (well under a cent/role) so a normal scan doesn't halt mid-run. Document the spend-ledger eviction limitation as a known non-durable-state issue (durable ledger = Stage 2; do not build now).

**3. Gate leaks (narrow).** Fix `\bprogram\b` matching "Engineering Program Manager"; deny unambiguous off-family titles (SDR, Account Executive). Do NOT deny whole departments (Sales S&O / GTM is a target family; ambiguous → route to LLM).

**4. Location filter in the gate (DECISIONS #50, owner-confirmed).** Deterministic pre-evaluation filter + update `config/location_policy.yaml`:
   - Allow: Western Europe broadly — UK (London), Germany (Munich/Hamburg/Berlin), Netherlands (Amsterdam), France (Paris), Ireland (Dublin — **only** Tier-1 brand / clear step-up), plus Copenhagen, Stockholm, Madrid, Milan, Lisbon, Zurich, Brussels, Vienna; Singapore; Australia (Sydney/Melbourne).
   - Skip: Canada, India, rest of APAC, LATAM, Middle East, South Africa, etc.
   - US: not auto-blocked, but skip unless Tier-1 company AND explicit sponsorship AND exceptional role.
   - Judge by **posted** location; multi-location posting passes if any allowed location is present. Keep distinct from visa `feasibility`.

**5. Hybrid Claude evaluator (DECISIONS #49).** Replace the stub: Claude supplies the four dimensions + role-specific alignments/gaps + real confidence + advisory band (PRD §5.6, forced tool output). Pydantic validation rejects malformed responses (B-12). CODE computes fit, blockers, feasibility, final band. Stamp real `model_version`/`prompt_version`; enforce `MONTHLY_MODEL_SPEND_CAP_USD` with spend logging; reuse material-hash cache. Real prompt in `app/prompts/role_evaluation_v1.md`. `ANTHROPIC_API_KEY` env-only; tests mock the provider.

**6. Disqualifying-requirement blocker (DECISIONS #51, owner-confirmed).** Add a `disqualifying_hard_requirement` hard blocker → `blocked`. Configurable list in `candidate_profile.yaml`: required CS/engineering degree as a stated minimum; required advanced/expert/professional programming or production software development as a core duty; required deep ML/data-science engineering. **Fires only on must-have / required / minimum-qualification language** (never "preferred", "a plus", "nice to have", "familiarity", "exposure to"). LLM detects must-have-vs-nice-to-have and emits it in `hard_blockers` with the quoted JD line; code enforces the override.

**7. Regenerate the precision label set (AFTER 3–6 land).** Run `sample-live-noise --gate-passers` so the gate-passer sample reflects the new location filter + disqualifier. Commit as `data/evaluation_set/live_noise_precision_set.yaml` (all `expected_recommendation: null`) for Lasse to label.

**8. Benchmark with the real evaluator.** After Lasse labels the precision set: run Claude once against curated 33 + precision set, **commit the `llm_cache`**, make `benchmark` + its test use the cached LLM provider (not the fallback), and state in the report which evaluator and which label set produced the numbers. Targets: recall ≥95% (curated) AND digest precision ≥80% (gate-passer set). Budget 1–2 prompt/weight calibration loops.

**9. Commit the tracked artifacts:** the labeled `data/evaluation_set/live_noise_labels.yaml` (gate-recall set, Otto-labeled), `data/evaluation_set/labeling_rubric.md`, `data/evaluation_set/gate_recall_skim.md`, and the `docs/briefs/*.md` updates.

**Then:** re-enable live email ONLY after precision ≥80% with Claude AND Lasse's sign-off. Confirm hosted CI green. Defer B-13 (brand_floor) to backlog.

---

Notes from the gate-recall pass (already labeled by Otto, for context):
- Of a random 150-role feed sample: 146 skip, 1 apply_now (LN-019 Airwallex Ops Strategy/London), 2 consider (LN-118 Mistral Deployment Strategist EMEA, LN-150 Airbnb Partner Ops/Dublin), 1 stretch (LN-098 Palantir Deployment Strategist/Copenhagen). Confirms the feed is ~97% noise, mostly wrong-location.
- LN-097 (Celonis Digital Transformation Consultant / Value-Engineering org) defaulted to `skip` (pre-sales). Owner may revisit.
