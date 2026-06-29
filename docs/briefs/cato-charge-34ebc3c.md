# Cato charge — review `34ebc3c` (evaluator calibration fix)

Context: the live evaluator first over-surfaced (firehose), then over-corrected (hid LNP-090, blocked LNP-020). Fix Loop 2 reports it resolved: curated recall 100%, **live recall 9/10**, **live precision 9/9**, LNP-090 → apply_now, LNP-020 → consider. Numbers are green; your job is to find what green hides.

**Primary question — mechanism fix or benchmark overfit?** This is the one that matters. Read the `34ebc3c` diff and confirm the fixes are *principled* (general band thresholds, general must-have-only blocker logic), **not** hand-tuned to pass the labeled rows. Red flags: literal "Revenue Strategy & Operations" string matches, company/title special-cases, LNP-ID references in code, thresholds nudged to exactly clear fit-82/69. If it gamed the benchmark, recall/precision are meaningless.

**Secondary checks:**
1. **Regression tests are non-vacuous.** The new tests (precision-hiding-recall, LNP-090 apply_now reachability, LNP-020 over-blocking) must *fail* if the bug is reintroduced — mutate/revert and confirm they catch it, not just pass green.
2. **Recall gate actually gates.** Confirm live Apply/Consider recall is computed correctly and the benchmark *fails* below 90% — not just printed.
3. **No firehose re-opening.** Relaxing the blocker/caps must not have leaked the skip set: confirm precision held because the ~138 skips are still excluded (skip or blocked), not quietly surfaced.
4. **Blocker still fires when it should.** The genuine disqualifiers (required CS degree + production-coding/advanced-Python/deep-ML must-haves, defense, US-no-sponsorship) must still block. Confirm the relaxation didn't blanket-disable #51.
5. **Loud fallback / cost cap intact** after the changes.

**Confidence caveat to weigh:** the live set has only ~10 positives (9/9, 9/10) — thin evidence. Note whether that's enough to trust before re-enabling email, or whether a larger labeled positive set is warranted.

Return the usual prioritized flags (🔴/🟠/🟡/🔵) + verdict. If clean, the gate to re-enable live email is owner sign-off.
