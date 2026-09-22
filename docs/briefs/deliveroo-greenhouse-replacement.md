# Deliveroo Greenhouse Replacement: Cato Review Proposal

Date: 2026-09-22. Status: proposed, not implemented or approved.

## Decision Requested

Review replacing the incomplete Deliveroo Ashby board with the existing Greenhouse
adapter, **after a controlled identity/freshness reconciliation**. Do not approve a
config-only switch. Deliveroo remains disabled and excluded from configured
coverage pending implementation review and an observed successful rollout.

This brief makes no feed changes, database writes, paid evaluations, or backfill
launch. It follows the [B-32 prereview](b32-backfill-prereview.md); the wider paid
backfill and other company decisions remain separate.

## Observed Evidence

Read-only public preflight on September 22:

| Feed | Result | Scope |
| --- | --- | --- |
| [Ashby `deliveroo`](https://api.ashbyhq.com/posting-api/job-board/deliveroo?includeCompensation=false) | 12 jobs / 12 unique IDs | Small, multinational residual catalog; not the former corporate catalog |
| [Greenhouse `deliveroo`](https://boards-api.greenhouse.io/v1/boards/deliveroo/jobs?content=true) | HTTP 200; existing adapter healthy; 129 normalized jobs / 129 unique IDs | Includes 62 roles at the London location plus one combined London location |

The [official careers role link](https://careers.deliveroo.co.uk/role/marketing-manager-promotions-and-incentives-8205993/)
still redirects to [Deliveroo Greenhouse](https://job-boards.greenhouse.io/deliveroo/jobs/8205993).
This is direct employer evidence for the replacement source, not a guessed token.

The prior audit and Actions history establish the change: Ashby returned 226 on
September 15, 224 on September 18, and 11 on September 19 and 20. Yesterday's
Greenhouse check returned 123 jobs, including 60 London roles. Today it returns
129. The endpoint is moving, so these are dated observations, not expected minima.
The cross-country residual Ashby jobs and matching API responses with/without the
compensation query parameter rule out a single-region filter or that parameter
as the explanation. An ATS migration/split is the supported inference; no public
company announcement confirming the cause has been found.

**Date risk:** today 122 Greenhouse jobs have `first_published` on September 18;
seven have September 21. Yesterday all 123 were clustered within 13 minutes on
September 18. Do not treat these migrated publication dates as proof of new roles.
`GreenhouseAdapter` currently prefers `first_published`, falling back to `updated_at`.

Current feed dates put all 129 inside the 21-day window. The deterministic gate
passes 42: **approximately 14 scoring minutes / $1.26** at the configured 20 seconds
and $0.03 per role, before retries or database overhead. This is a preliminary
upper estimate for this feed, not authorization to score: reconciliation with
known older postings may reduce it. Repeat item count, ETA and spend immediately
before any approved paid run and reconcile the monthly budget.

## Existing Code: Why A Source-Key Change Is Insufficient

- `app/db.py:upsert_source` keys sources by company, source type and source key.
  Switching `ashby:deliveroo` to `greenhouse:deliveroo` creates a new source and
  disables the old source's health record. It does not migrate posting identities.
- `upsert_postings` looks up `(source_id, source_job_id)`. Ashby UUIDs and
  Greenhouse numeric IDs therefore insert separate postings, each with a new
  `first_seen_at` and review record. `canonical_key` is stored, not a cross-source
  identity resolver.
- `_merge_multi_location_postings` operates only on the incoming batch. Its key
  includes `source_type`; the full normalized description and
  `_variant_material_signature` protect against false merges, but do not search
  historical postings from another ATS. Title/department alone is not identity.
- `app/services/material.py` hashes normalized title, locations, full cleaned
  description, department and employment type; source ID, URL and dates are not
  material. However, that comparison is reached only after an existing posting
  identity has been found. An exact hash across ATSs is useful matching evidence,
  not an existing automatic reconciliation feature.
- Even an unchanged existing posting has `posted_at` overwritten by incoming
  feed data today. Merely preserving a date once during cutover will not protect
  it on the following scan.
- Digest since-last suppression in `get_digest_rows` looks for prior evaluations
  with the same `job_posting_id` and `input_hash`. A new posting ID bypasses the
  protection against evaluator-only repeat alerts. Presentation-level location
  dedup does not preserve review state, age or notification identity.
- Disabling a source is not posting retirement: old `job_postings` remain open,
  and the current digest/Potential Matches reads do not filter source health.
  Scanning the new source cannot accumulate missing counts for the old source.
  Old-source leftovers need an explicit cutover disposition, not an assumption
  that health=`disabled` makes them disappear.

## Proposed Implementation Boundary

1. **Read-only reconciliation report first.** Compare the complete Greenhouse pull
   with historical Deliveroo Ashby postings, including unavailable records and
   persisted evaluations/reviews. Emit counts and a stable mapping classified as
   exact unchanged, approved material-change continuation, unmatched or ambiguous.
   Use unique full-material matches as automatic candidates. Location-label aliases
   and known ATS wrappers may be suggested for human review, not discarded by a
   broad fuzzy/title-only or boilerplate-prefix matcher. Multiple candidates stay
   ambiguous. The old local SQLite snapshot is not authoritative production state.
2. **Preserve canonical posting identity for confirmed continuations.** Keep the
   existing `job_postings.id`, evaluation history, review timestamps/reasons,
   first-seen date, shortlist and application references. Persist the old/new
   source-ID mapping and date provenance so both retry and subsequent scans resolve
   the same posting. Do not delete history or rewrite immutable application
   snapshots. An idempotent reviewed transaction must reject mapping conflicts.
3. **Protect age and change semantics.** Keep known original posting dates across
   the switch and later scans. When original publication is unknown, retain that
   uncertainty and the existing first-seen fallback; do not relabel a migration
   timestamp as original publication. An unchanged mapped JD neither reopens a
   human decision nor becomes a new-role alert. A confirmed substantive JD change
   follows the normal material-change/re-evaluation rules, not blanket suppression.
4. **Handle the initial cohort explicitly.** Unmatched is not proof of newness.
   Quarantine ambiguous matches from automatic merging and initial new-role alerts,
   with a visible reconciliation report and owner decision; never silently drop
   them. Persist the approved initial-cohort alert disposition so the next scan
   cannot release a suppressed duplicate. Later genuinely new Greenhouse IDs must
   remain eligible normally. Classify old-source-only records as unresolved or
   explicitly retired; do not infer closure from stopping the Ashby scanner.
5. **Enable only after Cato clears the implementation.** Change the company to
   Greenhouse `deliveroo`, regenerate the Profile config, run the approved cutover
   and first scan, and verify coverage and replay. No live schema changes by the
   builder: any necessary migration is separately reviewed and owner-applied.

Prefer this bounded reconciliation over a general fuzzy cross-ATS merger. If safe
identity/date mapping cannot be established, retain the coverage gap and manual
intake until the owner approves an explicit initial-cohort disposition.

## Required Regressions And Rollout Evidence

- Same role, different ATS IDs/URL and migration date: one canonical posting;
  original age, review state, evaluation history and application references intact.
- Replaying the mapping and two subsequent feed scans is idempotent and cannot
  overwrite preserved dates or leak another new-role notification.
- Known older-than-21-day role republished September 18 remains outside normal
  surfacing/backfill. Unknown original date remains first-seen, not invented.
- Source switch and profile-only rescore alone produce no role alert. A real JD
  change can re-surface under existing rules; a genuinely new post-cutover role
  produces exactly one alert. A quiet run still sends heartbeat/health warnings.
- Same title/department and long shared company boilerplate but distinct bodies
  stay separate. Conflicting language, credential, scope or location variants do
  not merge merely because their title matches. Ambiguous mappings are reported.
- Old-source-only records have an explicit visible disposition; no frozen duplicate
  cards, silent historical deletion, or blanket closure caused by ATS retirement.
- Partial failure/retry preserves approved mapping and alert state; failed fetches
  remain visible and never masquerade as zero jobs. Existing adapter invariants,
  recency, notification, review/application and profile-drift tests stay green.

Before enablement: Cato's implementation verdict, owner rollout approval, reviewed
mapping/dry-run report, current count/ETA/spend and sufficient reconciled budget.
After rollout: record imported/matched/ambiguous/unmatched counts, no duplicate
canonical roles, preserved review/application references, expected alert behavior,
and the actual source-run health/count. Only then call Deliveroo restored coverage.
