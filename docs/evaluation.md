# Evaluation & Calibration

The evaluator is a **decision-support tool calibrated to one candidate's strategy**, not a generic recruiter. Its quality is measured against a labelled benchmark before it is trusted.

## The benchmark

[`data/evaluation_set/evaluation_set.yaml`](../data/evaluation_set/evaluation_set.yaml) holds ~30 historical roles, each with the owner's ground-truth label. Categories:

`clean_apply · consider · stretch_fds · reach · cs_deprioritize · below_level · visa_blocked · technical_blocker · brand_deprioritize`

Each entry separates the **label** (the owner's judgment of whether to surface/pursue) from the **actual_outcome** (what really happened) — a role can be a correct `apply_now` even though it was later rejected.

## Why the edge cases matter

The benchmark deliberately includes the cases that distinguish encoded judgment from keyword matching:

- **Warm path beats a fit gap** — a Deployment Strategist *stretch* is `apply_now` when there's a warm intro.
- **Visa blocks a strong role** — a fit bullseye is `blocked` when it's US-only with no sponsorship; a high score must never override a hard blocker.
- **Brand outweighs fit + free visa** — a role that fits the candidate's transformation work *and* is zero-visa is still `skip` on trajectory. This is the hardest signal to learn.
- **Function over title** — the same company's Customer Success role is `skip` while its Partner Operations role is `consider`.
- **Title vs. scope** — a "Manager, RevOps" with associate-level scope is `below_level`.

## How the harness runs

1. Fetch the real JD from each entry's `jd_source` (or paste it).
2. Run the evaluator → `role_fit_score / feasibility / strategic_priority / recommendation`.
3. Compare to the labels. Measure: Apply/Consider **recall (target ≥95%)**, digest **precision (≥80%)**, blocker accuracy, fit-band agreement, evidence quality.
4. Weight false positives more heavily than false negatives for urgent alerts; keep recall high in the full review queue.
5. Tune **weights and rules** (in `config/scoring_policy.yaml`), not individual outputs. Version every change.

## Owner responsibility

The labels encode the owner's judgment — **review and confirm them before trusting the benchmark.** When the strategy shifts, create a new profile/scoring version rather than overwriting the one used for prior scores.
