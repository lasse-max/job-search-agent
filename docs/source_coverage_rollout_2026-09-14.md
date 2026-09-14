# Coverage Rollout: 2026-09-14

The owner requested a couple more company configurations. This batch enables
**ElevenLabs and Encord**, both Tier 2, through the existing Ashby adapter.
The next scheduled scan will ingest them; this audit performed no database writes
or paid model calls.

## Prior Batch Verification

Scheduled run `34752822989` on September 13 fetched all five prior additions
successfully: DoorDash 32, Canva 262, Glean 118, DeepL 60 and Magentic 9 postings.
It scanned 36 companies and sent the digest. The run was degraded due to a separate
HelloFresh read timeout, not a failure of the new feeds or email delivery.

## Current Public-Feed Audit

| Company | Catalog | Fresh (21 days) | Fresh gate-passers | Decision |
|---|---:|---:|---:|---|
| ElevenLabs | 246 | 37 | 8 | Enable |
| Encord | 37 | 7 | 4 | Enable |
| Quantexa | 30 | 10 | 3 | Keep disabled for a later batch |
| Synthesia | 56 | 16 | 0 | Keep disabled for a later batch |
| Cohere | 144 | 46 | 2 | Keep disabled for a later batch |

Each feed returned a healthy payload. Fetched count, normalized count and unique
source-job-ID count matched for every company. All postings supplied dates.
Counts use the production relevance gate and recency policy; passing the gate
does not mean the evaluator will recommend applying.

ElevenLabs currently includes Revenue Strategy & Operations - EMEA and Adoption
Strategist - APAC. Encord includes a London Operations Associate opening; its
scope and level still need evaluation. The other audited companies' current
fresh roles offered less obvious fit, so the owner-requested batch stays at two.

Source endpoints:
- https://api.ashbyhq.com/posting-api/job-board/elevenlabs?includeCompensation=false
- https://api.ashbyhq.com/posting-api/job-board/encord?includeCompensation=false

## Runtime and Coverage

The selected feeds add **283 postings**, of which **44 are fresh** and **12 reach
evaluation**. At the configured 20 seconds and $0.004 per evaluation, initial
scoring is approximately **4 minutes / $0.048**, before retries and database
overhead. Public fetching and normalization took about 8 seconds combined. The
$15 monthly cap remains configured; this estimate does not establish remaining
credit or current accumulated spend.

| Tier | Before | Enabled after this batch |
|---|---|---|
| Tier 1 | 12/20 (60%) | 12/20 (60%), including partial DoorDash coverage |
| Tier 2 | 16/45 (36%) | 18/45 (40%) |
| Tier 3 | 8/27 (30%) | 8/27 (30%) |
| Total | 36/92 (39%) | 38/92 (41%) |

These are configured coverage counts; successful live ingestion is confirmed
separately after the scheduled scan. The generated Profile data is refreshed from
the watchlist. No adapter, scorer, gate, version, schedule or database migration
changes are part of this batch. Ready for Cato review after verification.
