# Codex Brief — Hybrid LLM (Claude) Role Evaluator

**Status:** approved next slice (owner: Lasse). Supersedes the earlier two-slice plan (interim deterministic gate, then LLM). This is **one combined slice**: the title/department relevance gate, digest cap, and live-noise benchmark are folded in as components of the LLM evaluator slice, not a separate ship.

**Why:** the first live digest was a 1,064-role / 529-page firehose (~3% on-target; Payroll, Legal Counsel, Hardware Config Manager, SDR scored `apply_now` 79–86; confidence hardcoded 0.68; identical boilerplate alignments). Root cause: the deterministic stub matches family keywords against the whole JD text and can't tell an S&O role from Payroll/Legal/Sales. The PRD always intended a **hybrid** evaluator (DECISIONS #1; PRD §0.3, §5.5): Claude judges the dimensions + evidence; the deterministic layer does the math, blockers, and final band. This retires `uncalibrated_dev_stub_v1`.

**Build to** `docs/PRD.md` §5 + `ROADMAP.md`. Commit in small internal steps (large slice — keep diffs reviewable), pause for Cato re-review, log assumptions + the ADRs below in `DECISIONS.md`. **Do NOT** start Stage 2/3. **Live email stays OFF** until the precision gate clears (see Acceptance).

---

## Internal ordering (do in this order)

1. **Cost-bounding relevance gate + live-noise sampler first** — these unblock everything.
2. **Lasse labels ~150 real roles** (sampled from the 1,064 already in SQLite) — runs in parallel; this is the precision target Claude must beat. Labeling is the critical-path human dependency; start it the moment the sampler exists.
3. **Then build the Claude evaluator and calibrate** against the labeled set. Budget for 1–2 prompt/weight calibration loops before precision clears 80%.

## Work items

1. **Coarse cost-bounding relevance gate** (`relevance_decision` in `app/services/evaluate.py`). A role reaches the LLM only if its **TITLE or DEPARTMENT** (not description text) matches a target/approved-stretch family (PRD §4.4–4.6). Config-driven; skips logged with reason. This is a **high-recall cost bound, not a fit judge**: exclude only clearly off-family functions (Payroll, Legal Counsel, Hardware/SW Eng, SDR, Industrial Designer, Marketing, pure Sales); route anything **ambiguous through to Claude** — never drop on title alone where scope is unclear (PRD Decision #7). **Do not build a hand-tuned department-penalty matrix** — that's whack-a-mole; the LLM is the real discriminator.

2. **LLM call** (`evaluate.py`): for each role passing the gate, call Claude (default `claude-haiku-4-5`, model configurable via env) with the candidate profile + JD using structured/tool output returning the PRD §5.6 JSON. The LLM supplies: four dimension scores (role_family_fit, evidence_strength, scope_seniority, gap_manageability), **role-specific** alignments (real JD-requirement → candidate-evidence mapping), gaps, uncertainties, concise summary, a **real** confidence, and an advisory recommended band.

3. **Keep scoring deterministic** (§5.5): CODE computes final `fit_score` from LLM dimensions × `scoring_policy.yaml` weights; CODE applies existing hard blockers (technical-PM, security clearance, work-authorization/visa) as overrides; CODE sets the final recommendation band from `scoring_policy` thresholds. The model's band is advisory only.

4. **Schema validation** with pydantic (declared in `pyproject`, currently unused): ranges (fit 0–100, confidence 0–1), enums (recommendation/feasibility/severity), required fields. Malformed/refused responses are **REJECTED and logged (fail-loud)** — never fabricated or silently defaulted.

5. **Prompt**: replace placeholder `app/prompts/role_evaluation_v1.md` with the real, versioned prompt encoding the profile, target/stretch families, the deprioritize list (CS, quota-sales, junior, native-PM, deep-eng), honest gaps, and the "product/strategy vs. generic ops/CS/sales" distinction.

6. **Cost control**: enforce `MONTHLY_MODEL_SPEND_CAP_USD` (track spend; **HALT scoring with a clear logged reason** when exceeded — no silent overspend). Reuse the material-hash cache so only new/materially-changed roles are scored; never re-score cached roles. Persist the **real** model version in provenance (retire the dev-stub marker).

7. **Digest composition** (`app/services/digest.py`): rank by fit and **cap** `apply_now`/`consider` to top N (config-driven); render low-priority/blocked as a **one-line count, not cards** (FR1-09).

8. **Live-noise benchmark** (reproducible + CI-safe): a command that samples ~150 real postings from the existing scan into a labeled set Lasse annotates, then reports digest precision against it (reuse the offline harness). **Cache the LLM responses per eval-set role** (like the JD cache) so `job-agent benchmark` runs offline/deterministically in CI with no live calls. Retain the 33-role set for recall.

9. **Secrets**: `ANTHROPIC_API_KEY` from env only, never committed; tests mock the LLM (no live calls in CI, no key in repo/tests).

## Acceptance

- `evaluate_role` uses Claude for dimensions + evidence; code does final fit/blockers/bands; provenance shows the real model version.
- Schema validation rejects malformed model output (tested with a mocked bad response); cost-cap halt tested; caching/skip-unchanged tested — all with a **mocked** provider, CI green, no live API in CI.
- Re-benchmark: **recall ≥95%** on the 33-role set (PRD #11) **AND digest precision ≥80%** on the ~150-role live-noise set (PRD §3). Per-role confidence is real (varies); alignments are role-specific (not boilerplate); the Payroll/Legal/SDR/HR/Engineer roles from the live sample land in skip/blocked — not apply_now.
- **Live email re-enabled only as the final step, conditional on live precision ≥80% AND Lasse's sign-off**; otherwise stays in local-file fallback and we iterate on prompt/weights.
- No Stage 2/3 scope; ruff + unittest green; no secrets/PII committed.

---

## ADRs to add to DECISIONS.md (#47–49)

- **#47 — Live email paused until live-noise precision clears.** Remove `RESEND_API_KEY` + `DIGEST_RECIPIENT_EMAIL` secrets so `scan-all` falls back to local files. Reason: the first live digest surfaced Payroll/Legal/Sales as `apply_now`; live delivery on an unvalidated evaluator erodes trust. Reversible (re-add secrets after precision ≥80% + sign-off).
- **#48 — The 33-role curated benchmark is superseded for *precision* by a ~150-role live-noise set; curated set retained for *recall*.** Reason: curated recall 100% / precision 90% gave false confidence — it never tested rejecting the ~97% off-target real feed. Reversible.
- **#49 — Hybrid Claude evaluator replaces `uncalibrated_dev_stub_v1`.** Claude judges dimensions + evidence; code computes fit, applies blockers, sets bands (PRD §5.5). Reversible (interface keeps the deterministic fallback).
