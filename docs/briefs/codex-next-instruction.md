# Codex — next instruction (ordered)

> **STATE (live):** Steps 1–4 + 6 shipped in `a36ae0c` (loud fallback, cost math, gate leaks, location filter, hard-requirement blocker). Both label sets are now **labeled by Otto** (gate-recall `live_noise_labels.yaml`: 146 skip / 4 surfaced; precision `live_noise_precision_set.yaml`: 138 skip / 1 apply_now / 9 consider / 2 stretch) — **commit them**. REMAINING: add seniority ceiling **#52**; actually run Claude + populate `llm_cache`; switch `benchmark` to the cached LLM provider; calibrate to recall ≥95% + precision ≥80%. The LLM machinery exists (`c796a40`) but has never been run — that's the gap.
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
