# Ordered Coverage Rollout: 2026-09-22

Owner request: Batch A (Aleph Alpha, Cognition, Cohere, Decagon), then Batch B
(Grab, ServiceNow / Moveworks, Wise), then Nearmap, Plaid and Skyscanner. Delivery
Hero remains held. Deliveroo replacement is a separate Cato proposal, not enabled.

This is configuration of the requested existing adapters, not scoring or adapter
development. Public preflights use the production adapter, normalization, 21-day
recency policy and deterministic relevance gate. Count and projected scoring
ETA/spend are reported before each batch is enabled. No model calls, production
database writes or manual scan/backfill dispatches are part of these preflights.

Estimates use the configured 20 seconds and $0.03 per gate-passer, before retries
and database overhead. They are upper bounds before ingestion deduplication,
not application recommendations or a verified remaining monthly allowance.
September historical production spend remains unreconciled; see ADR 93. The
scheduled cap remains $30 and the paid backfill is still held.

## Batch A

| Company | Catalog / unique IDs | Fresh | Fresh gate-passers | Scoring ETA | Projected spend | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Cognition | 98 / 98 | 8 | 1 | 20 sec | $0.03 | Enabled |
| Cohere | 143 / 143 | 48 | 3 | 1 min | $0.09 | Enabled |
| Decagon | 145 / 145 | 20 | 1 | 20 sec | $0.03 | Enabled |
| Aleph Alpha | 0 / 0 | 0 | 0 | 0 | $0 | Held, not counted |
| Enabled total | 386 / 386 | 76 | 5 | 1.7 min | $0.15 | Three feeds |

All enabled records have a title, location, description, source URL and posted
date. Adapter health is healthy, HTTP 200, with exact normalized/unique ID parity.
Official company careers pages link or embed these public Ashby boards:
[Cognition](https://cognition.com/careers),
[Cohere](https://cohere.com/careers), and
[Decagon](https://decagon.ai/careers).

Aleph Alpha's configured [lowercase board](https://api.ashbyhq.com/posting-api/job-board/alephalpha)
and [official-link capitalization](https://api.ashbyhq.com/posting-api/job-board/AlephAlpha)
both return valid empty catalogs, versus 10 at the previous audit. The
[official homepage](https://aleph-alpha.com/en/) links the capitalized board,
whose embedded job catalog is also empty: this is a legitimate zero, not a
parser failure. It remains disabled and uncounted pending the owner's monitoring
choice. The current expected-volume minimum is at least one, so enabling an
empty board would create a recurring degraded warning. No health-policy change
is included in this rollout; the previous audit count is retained as history.

After Batch A: **44/92 configured**, Tier 1 **12/20**, Tier 2 **24/45**, Tier 3
**8/27**. Configured enablement is not yet proof of a successful scheduled scan.

## Batch B

| Company | Catalog / unique IDs | Fresh | Fresh gate-passers | Scoring ETA | Projected spend |
| --- | ---: | ---: | ---: | ---: | ---: |
| Grab | 427 / 427 | 178 | 41 | 13.7 min | $1.23 |
| ServiceNow / Moveworks | 667 / 667 | 371 | 0 | 0 | $0 |
| Wise | 422 / 422 | 183 | 66 | 22 min | $1.98 |
| Total | 1,516 / 1,516 | 732 | 107 | 35.7 min | $3.21 |

All three pass full summary-pagination/detail-fetch validation and normalize with
unique IDs. No missing publication dates. Measured public fetch times were 73,
110 and 71 seconds respectively (about 4.2 minutes total; no model spend).
[Grab careers](https://www.grab.careers/en/jobs/),
[Moveworks careers](https://www.moveworks.com/us/en/company/careers) and
[Wise careers](https://wise.jobs/) confirm the configured sources. All 77 distinct
Moveworks `sr_id` values are present in the combined ServiceNow catalog of 667;
coverage is established by IDs, not inferred from the acquisition.

ServiceNow's US finance rotation posting `744000150707379` has an empty description;
its ID/title/location/URL/date remain valid and the location gate excludes it.
More importantly, 38 fresh allowed-market records hit the existing
`government_defense_clearance_declined` gate with standard export-control
boilerplate mentioning government authorities. This is a potential calibration
false-negative, not a connector failure or proof of zero relevant openings.
Thirty of those 38 match only the standard export-control sentence; diagnostic
removal of that sentence from in-memory copies produces 28 gate-passers, including
Singapore GTM programs and sales operations. This is diagnostic evidence, not a
company-specific fix or the active cost estimate. Escalate a generic boilerplate
scope fix separately to Cato; this configuration-only rollout does not change gates.
The gate-passer counts for every company are scoring candidates, not recommendations.

After Batch B: **47/92 configured**, Tier 1 **12/20**, Tier 2 **27/45**, Tier 3
**8/27**. Next scheduled ingestion still needs to confirm real reach and health.

## Follow-On: Nearmap, Plaid, Skyscanner

| Company | Catalog / unique IDs | Fresh | Fresh gate-passers | Scoring ETA | Projected spend |
| --- | ---: | ---: | ---: | ---: | ---: |
| Nearmap | 35 / 35 | 11 | 0 | 0 | $0 |
| Plaid | 118 / 118 | 40 | 0 | 0 | $0 |
| Skyscanner | 5 / 5 | 3 | 1 | 20 sec | $0.03 |
| Total | 158 / 158 | 54 | 1 | 20 sec | $0.03 |

All normalize with unique IDs, complete title/location/description/URL/date and
healthy adapter checks. Nearmap full-detail fetch took eight seconds; each Ashby
fetch took about one second. Sources:
[Nearmap careers](https://www.nearmap.com/au/careers),
[Plaid's official London BizOps application link](https://plaid.com/careers/openings/business-operations/london-office/business-operations-3/),
[Skyscanner's current public board](https://jobs.ashbyhq.com/eb485598-6bf3-40a5-8560-d70150131305).

Skyscanner's old `skyscanner` org token returns 404. The replacement UUID board
identifies Skyscanner, its official website and candidate privacy policy, is not
marked as a demo, and matches all five API IDs exactly. Wider corporate-site
catalog parity is unverified (corporate jobs page access challenge, not bypassed).
This is configured public-board coverage, not proof of all company openings.
Nearmap coverage does not include its separately linked itel/Paycom subsidiary.

Two more existing recall gaps need separate general-rule review:

- Nearmap: all five fresh non-US roles are rejected at the Barangaroo, NSW location
  label, which denotes a Sydney suburb. A diagnostic location-alias substitution
  lets one through (Group Reporting Accountant); two then fail function and two
  hit the government gate. Do not claim an obvious high-fit loss from these data.
- Plaid: all four London records hit the government gate on military/veteran EEO
  text. Only Technical Support is fresh; BizOps was posted August 19 and is stale.
  Removing the exact EEO sentence diagnostically lets these records through. A
  generic boilerplate fix must preserve genuine defense/clearance exclusions.

## Coverage And Operating Cost

| Tier | Before | After | Target | Remaining gap |
| --- | ---: | ---: | ---: | ---: |
| Tier 1 | 12/20 (60%) | 12/20 (60%) | At least 18/20 (90%) | 6 more |
| Tier 2 | 21/45 (46.7%) | 27/45 (60%) | At least 36/45 (80%) | 9 more |
| Tier 3 | 8/27 (29.6%) | 11/27 (40.7%) | At least 17/27 (60%) | 6 more |

The nine added feeds raise configured enablement from 41/92 to **50/92 (54.3%)**.
Report by tier, not a blended success claim: Tier 1 is unchanged and the coverage
gate remains unmet. Aleph Alpha, Delivery Hero and Deliveroo remain disabled and
uncounted. Profile JSON is regenerated from the same watchlist.

All three batches total **2,060 postings, 862 fresh, 113 current gate-passers**:
about **37.7 scoring minutes / $3.39**, plus about five minutes of observed public
fetch work and database overhead. Scoring is not launched here. These are first
scan upper estimates before ingestion dedup; later scans should only score fresh
new/materially changed or eligible stale-evaluator records. The $30 cap remains
unchanged, and unknown historical monthly spend is not relabeled as zero.
Once pushed, these enables take effect at the next daily **06:00 UTC** scheduled
scan. Holding the separate backfill does not hold new-feed scoring in that run.
No manual dispatch is launched by this task; Cato should review the commits before
the next scheduled activation. Daily cadence and spend-cap code are unchanged.

## Review Boundary

The owner explicitly requested these named enablements in order. Cato remains the
independent reviewer of the rollout commits; no unrequested feed or adapter is
enabled. Deliveroo's Greenhouse migration requires its own identity/date/alert
reconciliation review before activation. The B-14 parser remains held until the
owner confirms 20-30 real non-Spam alerts in the dedicated Gmail inbox; no mailbox
access or parser work is included here.

Deliveroo's [separate Greenhouse replacement proposal](briefs/deliveroo-greenhouse-replacement.md)
is submitted for Cato review, not enabled by this rollout. It requires preserved
posting identity, age, review state and new-role alert semantics across the ATS
change; the migration-date cohort must not be advertised as newly posted roles.

## Verification

- Python 3.12.14: `python -m unittest discover -s tests`, 253 passed, including
  cached curated/live benchmark gates, source enablement holds and Profile drift.
- `python -m ruff check .`: passed.
- Web: `pnpm test` (3 passed), `pnpm lint`, `pnpm typecheck`, `pnpm build`: passed.
  Prebuild regenerated Profile JSON; the three Profile contract tests also passed.
- Independent Cato review is still required. Builder sanity checks do not close it.
- Pre-existing unrelated documentation edits remain outside these rollout commits.
