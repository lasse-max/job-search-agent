# Coverage Batch 2: 2026-09-15

Workstream B of `docs/briefs/search-broadening-coverage-batch-2.md`.

The preflight and cost correction were shown to the owner before enabling four
Tier-2 Ashby feeds. No paid source scan or live database write was performed.

## Preflight

| Company | Catalog / unique IDs | Fresh (21 days) | Fresh gate-passers | Scoring ETA | Projected spend |
|---|---:|---:|---:|---:|---:|
| Deliveroo | 226 / 226 | 96 | 40 | 13.3 min | $1.20 |
| Quantexa | 30 / 30 | 10 | 3 | 1 min | $0.09 |
| Synthesia | 56 / 56 | 14 | 0 | 0 | $0 |
| Lovable | 80 / 80 | 21 | 3 | 1 min | $0.09 |
| Total | 392 / 392 | 141 | 46 | 15.3 min | $1.38 |

All four feeds passed adapter health and normalization with catalog/ID parity;
all postings supplied dates. Counts use profile v4 and the production relevance
and recency rules. The cost estimate is now $0.03 per evaluation, based on the
fresh challenge-set measurements in Workstream A; retries and database overhead
are additional. This is not a claim about remaining scheduler spend allowance.
Synthesia has a healthy nonempty catalog, not a broken zero feed; enabling it
monitors future suitable openings without forcing evaluation today.

Deliveroo includes Global Program Manager, Product / CX / Automation and Strategy
& Operations Manager roles. Passing the gate is not an application recommendation.
Public endpoints use `https://api.ashbyhq.com/posting-api/job-board/{source_key}`
with keys `deliveroo`, `quantexa`, `synthesia`, `lovable`.

## SafetyCulture

Lever `safetyculture-2` still returns a valid empty array. Lever `safetyculture`
and Ashby `safetyculture` return 404. The official careers request was rate-limited;
search-indexed Lever results from one/two months ago do not prove a live catalog.
SafetyCulture remains disabled with an updated note. No differently branded
Mitti catalog is substituted for full company coverage.

## Coverage and Prior Rollout

| Tier | Before | Configured after | Target |
|---|---|---|---|
| Tier 1 | 12/20 (60%) | 12/20 (60%) | 90% |
| Tier 2 | 18/45 (40%) | 22/45 (49%) | 80% |
| Tier 3 | 8/27 (30%) | 8/27 (30%) | 60% |
| Total | 38/92 (41%) | 42/92 (46%) | Tier-weighted targets above |

Daily cron remains `0 6 * * *`. The next scheduled run must verify these four
new sources; configured enablement is not successful ingestion. The previous
rollout is confirmed by run `34837391308`: ElevenLabs fetched 246, Encord 37,
scan status success and notification sent. DoorDash remains regional coverage.

## B-14 and Review

Read-only production preflight `34923226816` on commit A confirmed
`transaction_read_only=on` and **255 fresh stale-policy candidates**: **5,100
seconds (85 minutes), projected $7.65**. These are all eligible stale-profile
roles, not just newly matched Program Management titles. Adding the 46 new-feed
candidates gives roughly **301 evaluations / 100 minutes / $9.03**, before
retries and any new daily arrivals. No full backfill was dispatched; the existing
per-source batch limit and monthly cap remain. Scheduled spend already consumed
is not available from this read-only count, so $15 configured is not $15 remaining.

Only dedicated-mailbox contracts and synthetic boundary tests are scaffolded.
The mailbox and real sample formats have not been confirmed; no personal inbox,
OAuth, production parser, scheduler wiring or extra coverage claim is introduced.
See `docs/briefs/email-alert-ingestion-scaffold.md` for the owner prerequisite and
next implementation boundary.

Cato: review source/config parity, owner-visible cost correction, disabled
SafetyCulture, generated Profile equality, and the fail-closed mailbox binding.
