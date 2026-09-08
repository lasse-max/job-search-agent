# Coverage Rollout: 2026-09-08

The owner requested ingestion repairs and increased coverage. This enables five
revalidated feeds using existing adapters. It does not run a paid backfill.
The next scheduled scan consumes the new configuration.

| Company | Tier | Feed | Fetched and normalized | Fresh | Fresh gate-passers | Estimated scoring |
|---|---:|---|---:|---:|---:|---|
| DoorDash | 1 | Greenhouse `doordashaustralia` | 33 | 6 | 3 | 1 min / $0.012 |
| Canva | 1 | SmartRecruiters `Canva` | 269 | 115 | 25 | 8.3 min / $0.100 |
| Glean | 2 | Greenhouse `gleanwork` | 115 | 19 | 0 | 0 |
| DeepL | 2 | Ashby `deepl` | 64 | 23 | 6 | 2 min / $0.024 |
| Magentic | 2 | Ashby `magentic` | 7 | 1 | 0 | 0 |
| Total | | | 488 | 164 | 34 | 11.3 min / $0.136 |

All counts use the production adapters, relevance gate and 21-day recency policy,
without persisting postings or calling the model. Missing posting dates use the
prospective first-seen date, as in ingestion. Fetching/normalizing took about 39
seconds total. Scoring projections use the configured 20 seconds and $0.004 per
evaluation; retries, database latency and other existing sources are additional.
The configured $15 monthly limit remains unchanged; this is not a claim about
remaining account credit or already-spent model budget.

Canva reconciled its complete paginated list and detail responses. DoorDash is
explicitly Australia-only; other DoorDash catalogs remain a coverage gap.
Zero gate-passers at Glean/Magentic is a valid current outcome, not an empty feed.

## Enabled Coverage, Pending First Scheduled Scan

| Tier | Before | After |
|---|---|---|
| Tier 1 | 10/20 (50%) | 12/20 (60%), including partial DoorDash coverage |
| Tier 2 | 13/45 (29%) | 16/45 (36%) |
| Tier 3 | 8/27 (30%) | 8/27 (30%) |
| Total | 31/92 (34%) | 36/92 (39%) |

Configured enablement is not proof of a successful scheduled run. Live reach now
counts only current configured source identities with actual attempts, excluding
manual sources, retired feeds and repeated same-day attempts. Profile and
Potential Matches share that calculation. With no durable scan-batch ID, reach
is the latest attempt per source on the most recent UTC scan day.

## Failed Revalidation

SafetyCulture's previously validated Lever `safetyculture-2` now returns zero.
Ashby `safetyculture` returns 404. The configured official careers/jobs URLs
redirect to Mitti-branded pages, which link an Ashby `mitti` catalog. Those links
do not establish full SafetyCulture catalog coverage. SafetyCulture remains
disabled and visibly marked as a dead feed, pending verified company scope.

Both Black Forest Labs and Mistral succeeded in the September 7 and 8 scheduled
logs after their prior repair. The September 8 scan and email completed.

## Most Efficient Next Work

1. Verify SafetyCulture's actual company catalog before changing its source key.
2. Capture the remaining bespoke Tier-1 companies through the already-planned
   dedicated job-alert mailbox: Google, Apple, Amazon, Uber, Netflix, Atlassian,
   and NEURA. Manual intake is a bridge and is not automated coverage.
3. Roll out more small, already-supported Ashby feeds in batches of three to five,
   with a fresh count/ETA/cost preflight. Prioritize Tier 2 before high-volume
   Tier 3 feeds such as Delivery Hero.
4. Audit narrow feeds such as Disney and LinkedIn for catalog parity. A successful
   response alone does not establish complete employer coverage.

Daily scheduling, evaluator version, scoring, bands and digest caps are unchanged.

## Manual Intake: Confirmed Live Prerequisite

Read-only Actions diagnostic run `34224052140` confirmed
`transaction_read_only=on`. Both `remove_manual_intake(integer)` and
`replace_manual_intake_with_url(integer,text,text,text,text,text,text,boolean)`
are absent. The owner must apply
`migrations/009_stage15_manual_intake_controls.sql` before Remove/Redo can work.
The diagnostic made no database writes. It can be rerun afterward to verify both
functions exist, authenticated execution is granted and anonymous execution is not.

There are two completed manual submissions and one failed URL submission carrying
an old HTTP 400 error. The old implementation discarded the provider response
detail, so the original cause cannot be established from that record. A minimal
Claude API probe now succeeds. The new error classification and page-code
exclusion improve diagnosis and prevent oversized script-heavy extraction; they
are not evidence of the original request's cause.

Cato review focus: read-only enforcement, missing-RPC error classification, no
provider/credential leakage, preservation of visible JD requirements, current-feed
reach reconciliation, and regional/catalog caveats in this rollout.
