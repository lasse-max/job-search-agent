# Retired Sources And Controlled Backfill: Cato Handoff

Date: 2026-09-28. PR only. No paid backfill, retirement or migration applied.

## Launch Status

**Owner update, 2026-09-28:** drop the console-MTD seed. Once Cato clears this PR
and it merges, launch the single full backfill with the retained Actions ledger
and the unchanged **$30 cap**. Do not request a console number, replace the ledger,
raise the cap, or launch an unreviewed branch. Deliveroo Greenhouse stays excluded.
The earlier reconciliation prerequisite (ADR #103) is superseded by ADR #105;
seed inputs, receipt cache and month-specific cap overrides are removed.

Read-only preflight on reviewed `main`:
[run 36417083490](https://github.com/lasse-max/job-search-agent/actions/runs/36417083490)
completed with server-enforced `transaction_read_only=on`: **46 pending roles,
920 seconds (15m20s) scoring, $1.38**, under the 21-day policy. This replaces the
dated 255-role estimate. That older preflight does not report inactive-source
counts; the extended PR preflight must supply those before launch. Its new v5
policy also reopens fresh older-policy skips, so do not reuse 46 as its launch count.

Recent completed scan artifact ledgers were $6.028048 (Sep24), $6.856984 (Sep25),
$7.562933 (Sep26), and $8.439607 (Sep27). The verified daily deltas are $0.828936,
$0.705949, and $0.876674. These are incremental planning evidence, **not console
MTD**. Reserve **$3.30** for up to three remaining September scans: maximum observed
daily cost times three, plus 25%, rounded up. Those scans took approximately
125/120/112 minutes end to end, so scoring-only ETA omits substantial fetch/DB time.

The last observed tracked MTD of $8.439607 plus the PR's $13.14 backfill estimate
and $3.30 reserve is **$24.879607**, under the fixed $30 runaway guard. This is a
ledger-based projection, not an accurate September provider bill. Refresh the
read-only item count/ETA/cost before dispatch; leave the ledger itself untouched.
October automatically starts a new UTC-month bucket, but complete accounting still
depends on cache retention and token-price estimates, not a calendar reset alone.
The new before-run snapshot and existing after-run ledger artifact allow an actual
tracked-spend delta to be reported after the job. Do not describe it as invoiced cost.

## Changes For Review

- Python live digest/review/detail/opportunity exports/sampler/backfill and web
  matches/detail/shortlist/all-role audit exclude disabled/retired, disabled-company,
  unknown-auto and replaced ATS/key sources. Current failing/degraded feeds remain
  visible. Watchlist checks protect reads before stale DB metadata is reconciled.
- Owner-selected manual roles are independent of automatic watchlist enrollment.
  Manual and automatic sources no longer disable each other during upsert. An
  explicitly disabled manual source remains hidden and is visible in reconciliation.
- Source coverage/run exports, backups and immutable Applied history remain intact.
  These are historical/audit reads, not a live opportunity feed.
- `010_stage15_active_source_reads.sql` is owner-applied after review. Both it and
  the runtime canonical `001` view enforce source state and owner/RLS boundaries;
  a cross-check prevents the next scan's schema bootstrap from undoing 010. SQL
  cannot read YAML identity directly; web/Python checks plus explicit retirement
  cover unsynchronized config. Shortlist/new-application RPCs inherit the view guard.
- Generic export-approval noun phrases are removed before government-scope checks,
  regardless of whether the subject is applicants, the company or the role. A real
  adjacent clearance/government duty remains enforceable. `location_policy_v5`
  also adds state/canton context codes, including Oerlikon/ZH, and reopens only fresh
  stale-policy rows. No employer exceptions or model-version bump.
- Login help identifies the owner's Supabase password, not their email password;
  no signup, reset, credential exposure or authorization change.
- Actions restores/saves the existing ledger under the same cache key/path and uses
  the unchanged $30 cap. Full backfill has no seed prerequisite. A read-only copy
  into `output/model_spend_before.json`, uploaded with the post-run ledger, records
  the baseline for spend reporting without resetting or adding to the ledger.
  Cache-miss warnings remain loud; no invoice accuracy or durable billing is claimed.

## Explicit Retirement

Default command is read-only, including server-enforced read-only Postgres or
SQLite `mode=ro`/`query_only`. It never creates a missing SQLite DB:

```sh
job-agent retire-sources --report output/source_retirement.json
```

The report identifies each source, exclusion reason, open posting IDs and a plan
hash. Review the entire report, including any previously disabled manual sources,
before the owner explicitly applies it with the production connection configured:

```sh
job-agent retire-sources --apply-report output/source_retirement.json
```

Apply rechecks identity/current inactivity and new postings under a short write
lock. A stale/modified plan refuses; a successful replay changes zero rows. It sets
postings unavailable and source health disabled, never deletes data or changes
review decisions, dates, evaluation history or application snapshots. Any new
postings after the report require another report. No automatic retirement is added
to scanning. No builder production retirement or schema writes were performed.

## Review Gates

1. Source predicates operate before live query limits and retain failing/degraded
   sources and legitimate manual roles. Applied history is not version/source-filtered.
2. Retirement is report-first, atomic and retry-safe; no hidden historical deletion.
3. Export variants no longer false-block, but genuine mixed-clause disqualifiers do.
4. No ledger replacement or cap override exists in the launch path. The snapshot
   never mutates/creates the source ledger, and the daily cron stays 06:00 UTC.
5. Re-run the extended **read-only** production preflight, inspect excluded-source
   counts/report, then use fresh item count, full ETA and cost for the one paid run.
   Do not launch it from the unreviewed PR branch or enable Deliveroo.

Offline cached benchmarks pass unchanged: curated33 recall100%, precision94.7%,
blocker100%, exact20/33; uniform150 gate recall100%; gate-passer150 Apply/Consider
recall/precision100% (six positives), all-surfaced precision75%. These are historical
Claude-cache replays, not fresh paid prompt/profile calibration. Labels/caches unchanged.

Validation before the owner update: Python 3.12 full unittest suite passed (288 tests), followed by
22 focused tests after the final manual-source regression. Ruff and diff checks
pass. Web tests, lint, typecheck and production build pass; Profile JSON/YAML drift
checks pass. GitHub CI and the extended production preflight are recorded below
after the review branch is pushed. These builder checks do not replace Cato review.

## Production Evidence For The PR

Code commit: `a6d1507`. [PR #1](https://github.com/lasse-max/job-search-agent/pull/1).
Both Python/Ruff and web CI passed in
[run 36418815009](https://github.com/lasse-max/job-search-agent/actions/runs/36418815009).

The extended read-only production preflight completed in 3m39s:
[run 36418831448](https://github.com/lasse-max/job-search-agent/actions/runs/36418831448),
2026-09-28 12:01 UTC. It uses the **proposed PR policy**, not reviewed main:
`hybrid_claude_v4|candidate_profile_v4|location_policy_v5|scoring_policy_v2|recency_policy_v2`.

| Planning result | Count / estimate |
| --- | --- |
| Fresh current-source roles selected | 438 |
| Disabled/retired-source roles in selection | 0 |
| Fresh stale candidates excluded from inactive sources | 45 |
| Of those, relevance-gate passers excluded | 18 |
| Scoring-only ETA | 8,760 seconds / 2h26m |
| Scoring-only spend estimate | $13.14 |
| Practical end-to-end planning window | Roughly 4-5 hours, including recent fetch/DB overhead |
| Remaining September scan reserve | $3.30 |
| Tracked month-end projection before unplanned feed growth | $8.439607 + $16.44 = $24.879607 |

The additional policy revision makes existing fresh older-policy evaluations/skips
stale again, explaining why this is larger than main's 46-role plan. Do not launch
the main plan and then another PR plan: after Cato clearance and merge, refresh this
read-only count, then launch once with the retained ledger. No console number is
required; the fixed $30 cap remains enforced and must not be raised automatically.

All 45 excluded fresh candidates (18 gate passers) are from disabled Deliveroo
Ashby. Old Mistral Lever, Black Forest Labs Greenhouse and disabled Atlassian each
have zero fresh stale candidates. Deliveroo Greenhouse remains out.

The separate all-age retirement report identifies **411 open historical-source
postings**, not 411 backfill candidates:

| Source | Open postings proposed for closure |
| --- | --- |
| Mistral AI, old Lever / mistral | 172 |
| Black Forest Labs, Greenhouse / blackforestlabs | 17 |
| Deliveroo, disabled Ashby / deliveroo | 222 |

[Download the reconciliation artifact](https://github.com/lasse-max/job-search-agent/actions/runs/36418831448/artifacts/10967294662).
Its source counts sum to 411. Plan hash:
`45fbb631dfe1ba32f352cd0d1b85991f25a176befb902656c6416f3321a4e458`.
No disabled manual source appeared in this production report. No retirement,
migration, ledger replacement, cap increase, model call or email was performed.

## Post-Merge Launch And Reporting

1. Confirm Cato cleared the final PR revision and the owner merged it, with CI green.
   CI success by itself is not Cato clearance. Do not merge on the owner's behalf.
2. Check workflow history for an already-dispatched full backfill, including failed
   or running attempts. Never dispatch the authorized full pass twice automatically.
3. Refresh the read-only preflight on merged `main`; report count, end-to-end ETA,
   projected spend and inactive-source exclusions. Deliveroo stays out.
4. Dispatch `scan.yml` on `main` with `full_stale_backfill=true`, no other budget
   inputs. Record the run ID immediately. Keep the ledger/cache and $30 cap intact.
5. On completion, compare `output/model_spend_before.json` with the uploaded
   `data/model_spend_ledger.json`, by UTC month if the run spans a month boundary.
   Report the tracked run delta, ending tracked MTD, completed/deferred work and
   any cap stop or scan/email failure. A missing baseline/artifact makes the delta
   unavailable, not zero. Do not retry a partial run or increase the cap silently.
