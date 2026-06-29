# Evaluation & Calibration

The evaluator is a **decision-support tool calibrated to one candidate's strategy**, not a generic recruiter. Its quality is measured against a labelled benchmark before it is trusted.

## The benchmark

[`data/evaluation_set/evaluation_set.yaml`](../data/evaluation_set/evaluation_set.yaml) holds ~30 historical roles, each with the owner's ground-truth label. Categories:

`clean_apply · consider · stretch_fds · reach · cs_deprioritize · below_level · below_level_by_scope_not_title · visa_blocked · technical_blocker · brand_deprioritize`

Each entry separates the **label** (the owner's judgment of whether to surface/pursue) from the **actual_outcome** (what really happened) — a role can be a correct `apply_now` even though it was later rejected.

## Why the edge cases matter

The benchmark deliberately includes the cases that distinguish encoded judgment from keyword matching:

- **Warm path beats a fit gap** — a Deployment Strategist *stretch* is `apply_now` when there's a warm intro.
- **Visa blocks a strong role** — a fit bullseye is `blocked` when it's US-only with no sponsorship; a high score must never override a hard blocker.
- **Brand outweighs fit + free visa** — a role that fits the candidate's transformation work *and* is zero-visa can still be `skip` on trajectory. This signal is surfaced in the profile/benchmark; scoring is deferred to the calibrated LLM evaluator.
- **Function over title** — the same company's Customer Success role is `skip` while its Partner Operations role is `consider`.
- **Title vs. scope** — a "Manager, RevOps" with associate-level scope is `below_level_by_scope_not_title`.

## How the harness runs

1. Fetch the real JD from each entry's `jd_source` (or paste it).
2. Run the evaluator → `role_fit_score / feasibility / strategic_priority / recommendation`.
3. Compare to the labels. Measure: Apply/Consider **recall (target ≥95%)**, digest **precision (≥80%)**, blocker accuracy, fit-band agreement, evidence quality.
4. Weight false positives more heavily than false negatives for urgent alerts; keep recall high in the full review queue.
5. Tune **weights and rules** (in `config/scoring_policy.yaml`), not individual outputs. Version every change.

## Owner responsibility

The labels encode the owner's judgment — **review and confirm them before trusting the benchmark.** When the strategy shifts, create a new profile/scoring version rather than overwriting the one used for prior scores.

## Calibration case study — June 2026 (interview-ready)

A worked example of "measure the right thing, not the convenient thing," across four review loops. Each failure was caught by reading the actual roles, not the green metric.

1. **The benchmark measured the wrong thing.** The first benchmark (33 hand-curated roles: 100% recall, 90% precision) looked green, so the deterministic stub was wired to live email. The first real run produced a **1,064-role / 529-page firehose** — Payroll, Legal, Sales, Engineering all "apply now." The curated set was pre-filtered to on-target roles, so it never tested rejecting the ~97% off-target majority of a real feed. *Lesson: a benchmark is only as honest as the distribution it samples.*
2. **Split the eval by purpose.** Replaced the single curated set with two purpose-built ones: a **gate-recall** set (uniform random sample — is the gate hiding good roles?) and a **gate-passer precision** set (roles that actually reach the digest — does the evaluator reject the noise the coarse gate lets through?). Precision is now measured where it's decided.
3. **Precision can hide a recall miss.** After swapping in the Claude evaluator, "precision 6/6 = 100%" hid that only ~6 of ~10 wanted roles surfaced (the evaluator over-corrected to too-stingy, demoting the strongest role and false-blocking a clean one). Fix: **gate on recall and precision together** — neither alone can pass.
4. **The metric must match what's delivered.** Reported precision counted only apply/consider, but the digest also sends a `stretch` section — so skip-labeled roles promoted to stretch were invisible to the number. Fix: report **all-surfaced precision (incl. stretch)** alongside the gated apply/consider number, so the metric can't claim "clean" while the inbox shows noise.
5. **Independent review beats self-certification.** The builder (Codex) and reviewer (Claude Code) are deliberately *different tools*; the reviewer mutation-tested every regression fix and caught a blocker that under-fired on phrasings other than the literal word "required" — a bug invisible in the aggregate pass. The role separation, not the tool, is what caught it.

Backstops that make a firehose structurally impossible regardless of evaluator quality: a deterministic relevance gate (location + function + L4–L5 seniority), narrow hard blockers, and a hard digest cap (25/50, loud-not-silent).
