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

## Review Boundary

The owner explicitly requested these named enablements in order. Cato remains the
independent reviewer of the rollout commits; no unrequested feed or adapter is
enabled. Deliveroo's Greenhouse migration requires its own identity/date/alert
reconciliation review before activation. The B-14 parser remains held until the
owner confirms 20-30 real non-Spam alerts in the dedicated Gmail inbox; no mailbox
access or parser work is included here.
