# B-32 and Backfill Prerequisites

Date: 2026-09-21. One builder commit, then pause for Cato. No paid backfill,
live database writes, or replacement-feed enablement in this pass.

## Review Responses

- **B-32: fixed, requesting re-review.** All four owner examples are non-blocking
  through the shared JD/LLM-evidence detector. Negation is matched next to the
  technical requirement, not applied to the whole fragment. Genuine production
  coding and technical-degree requirements still enforce even beside negated
  requirements or unrelated "no travel required" text. A candidate's missing
  coding background is not mistaken for an optional JD requirement. SB-04 is now `skip`, not
  an unjustified `blocked`; its fit remains 33. The challenge test now requires
  every negative example to be `skip`, not either `skip` or `blocked`.
- **Fail-loud tests: fixed, requesting re-review.** Two tests run the real
  scheduler through CLI `main`: a scan exception with successful email still
  exits 1; a successful scan with failed delivery exits 1. Removing either
  scheduler `failures.append` branch independently makes its regression fail.
  Existing source-level failure/degraded-warning tests still expect exit 0.
- **Deliveroo coverage: withdrawn; replacement deferred for Cato.** Details below.
- **Spend cap: $30 configured.** Added prospective ledger retention and serialized
  scans after discovering the previous CI ledger reset. Historical MTD is unknown,
  not zero, and must be reconciled before the held paid backfill.

## Deliveroo Re-audit

The feed is not truncated by the adapter or limited to one country. Both
[Ashby endpoint variants](https://api.ashbyhq.com/posting-api/job-board/deliveroo)
return 11 warehouse/site jobs across the UK, Italy, UAE and France.

Observed Actions history:

| Scan | Ashby fetched | Finding |
| --- | ---: | --- |
| [Sep 15](https://github.com/lasse-max/job-search-agent/actions/runs/34959375698) | 226 | Audit reproduced |
| [Sep 18](https://github.com/lasse-max/job-search-agent/actions/runs/35333816133) | 224 | Still broad |
| [Sep 19](https://github.com/lasse-max/job-search-agent/actions/runs/35436123850) | 11 | Degraded, expected minimum 45 |
| [Sep 20](https://github.com/lasse-max/job-search-agent/actions/runs/35504697839) | 11 | Still degraded |

The [official careers page](https://careers.deliveroo.co.uk/) now links corporate
roles to [Greenhouse](https://job-boards.greenhouse.io/deliveroo/jobs/8205993).
The [Greenhouse public feed](https://boards-api.greenhouse.io/v1/boards/deliveroo/jobs?content=true)
preflight returned HTTP 200, healthy, 123 jobs / 123 unique normalized IDs, including
60 London roles. This supports an ATS migration/split, although its cause is an
inference, not a company announcement.

Options:

1. **Implemented:** disable Ashby, exclude Deliveroo from coverage, use manual intake.
   Coverage is 41/92 (45% rounded); Tier 1 12/20, Tier 2 21/45, Tier 3 8/27.
2. **Recommended after review:** migrate to the already-supported Greenhouse adapter.
   Current preflight is 40 fresh gate-passers, about 13.3 scoring minutes / $1.20
   at the configured 20 seconds / $0.03 per role, before retries and DB overhead.
   All 123 `first_published` timestamps cluster within 13 minutes on September 18.
   Treat those as potential migration dates, reconcile prior Ashby identities and
   known age first, and prevent duplicate new-role alerts. Do not call all 123 new.
3. Keep residual Ashby only if frontline hiring later becomes relevant. It does
   not currently represent the requested corporate-role coverage.

## Spend and Launch Gate

- Local September tracked estimate: **$0.613536**. This is not production/account MTD.
- Production September MTD: **unavailable from retained app evidence**. Twenty
  successful daily runs through September 20 retained no ledger or per-run usage.
  Evaluation caches/rows do not retain billing tokens or cost. The owner has been
  asked for the Anthropic console's September workspace/API-key usage amount.
- The old cap effectively reset each hosted run. New workflow restores and saves
  the ledger, including after scan failures, and serializes scans so two jobs do
  not overwrite each other's tracked spend. Cache misses are loud warnings.
- This does not recover historical spend or make cache state durable. Do not
  infer `$30 - $0.61` remaining. Provider billing is authoritative; the ledger uses
  estimated token costs. No change to provider model or rate assumptions here.
- **Backfill stays held until Cato clears this commit and the owner approves the
  production step.** The September 15 read-only plan was 255 roles / 85 minutes /
  $7.65 for backfill alone (roughly $9 including new-feed work). It is now dated:
  repeat the read-only count/ETA/spend preflight against the then-current 21-day
  window and enabled feeds before launch. Reconcile remaining budget first.
- Do not enable Greenhouse Deliveroo in that launch without its separate review.
  Every feed enablement gets Cato review; no repeat of unreviewed `c2e1522`.

## Verification

Cached benchmark gates are unchanged: curated recall 100%, Apply/Consider
precision 94.7%, blocker accuracy 100%; live-set Apply/Consider recall and precision
100%, all-surfaced precision 75% report-only; uniform gate recall 100%. These are
historical Claude v6 response replays under current policy, not new paid judgments.
The separate nine-case challenge replays the existing v7/profile-v4 cache: all
three business positives surface and all six scope negatives skip, including SB-04.
No owner labels or model caches were changed and no paid calls were made.

Local verification: 253 Python tests passed (including the profile-config drift
guard); ruff, web tests, lint, typecheck and production build passed. Removing the
negation guard in memory causes six negative subtests to fail. Both scheduler
exit-status mutations independently fail their new CLI regressions. CI must also
pass on the pushed commit. Cato remains the independent reviewer; builder
regression and mutation checks do not constitute final approval.
