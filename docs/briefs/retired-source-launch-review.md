# Retired Sources And Controlled Backfill: Cato Handoff

Date: 2026-09-29. PR only. No paid backfill, retirement or migration applied.

## Second-Review Fix Round

Cato's verdict at `789befa` was HOLD. This round implements all ten items in
`docs/briefs/pr1-backfill-runtime-guard.md`; the following are builder fixes for
independent re-review, not self-closed findings:

1. **Paid crash durability:** commit after each completed evaluation. Cato's exact
   two-paid-results-then-crash scenario now preserves both results and the ledger;
   retry calls the provider only for the remaining roles. Interrupted new/material
   work in days 15-21 remains discoverable without widening policy-only backfill.
2. **Runtime bounds:** one monotonic 270-minute evaluation budget across sources,
   both full and daily modes. Finish the current evaluation, stop new scoring,
   retain source/run health, defer manual intake and send the digest/heartbeat.
   Source warnings and the aggregate report give evaluated/remaining counts;
   expiry is degraded and CLI exit 0, not a failed scan. Fake-clock tests exercise
   expiry and exact newest-first resume without duplicate paid calls.
3. **Timeout/ledger:** `270 < 315 (scan step) < 330 (job) < 360 (runner)`.
   The earlier step timeout leaves cleanup headroom inside the job, minus setup
   time. Ledger increments are flushed atomically per charged result; the same
   cache restore/save paths, fixed $30 cap and `always()` artifact/ledger steps
   remain. Ordinary cancellation cleanup is best-effort, not a guarantee against
   force-cancel, runner loss or job timeout. No console reconciliation gate exists.
4. **UTC recency:** normalize timestamps before the 14-day selector's filter,
   newest-first order and LIMIT, and the 21-day digest/web filters. Preserve raw
   historical source strings. Shared SQL expression plus typed view `effective_at`
   prevent lexical offset errors; chips count UTC calendar days. Owner migration
   010 appends this column and must precede deploying the web read path.
5. **Retirement:** new owner-only/manual `retire-sources.yml`, exact approval hash,
   read-only regeneration, locked recheck, and shared scan concurrency. Report v2
   includes owner-touched review/application history in its hash. Wrong hashes
   write nothing; replaying a report changes zero actual DB rows. A workflow rerun
   with a successfully consumed hash refuses read-only and prints the new empty
   plan hash, rather than silently authorizing any newly arrived roles.

Otto's seven documentation edits were moved byte-for-byte to a separate docs-only
`main` commit, `a10f14d`. B-30 through B-33 already occurred once each; no rows were
dropped. They are not mixed into the PR's implementation commits. ADRs 107-109
record the checkpoint, timestamp and retirement choices.

Implementation commits for this round:

- `f31e8ce`: retirement report v2, exact-hash owner workflow, zero-write replay.
- `fc06bdd`: UTC recency across Python/SQL/web and interrupted-material selection.
- `de14451`: per-evaluation checkpoint, atomic ledger, shared runtime budget,
  timeout headroom, degraded counts and digest/heartbeat warning.

Targeted verification includes Cato's two mutation checks: deleting the primary
evaluation commit fails the crash regression (zero instead of two saved), and
disabling the deadline check fails the budget regression (five instead of two
provider calls). Wrong-hash and retirement-replay tests assert actual database
changes. Real disposable local PostgreSQL 16 checks passed with a non-UTC session,
mixed-offset cutoff/limit queries and bootstrap/migration view replacement; no
Supabase connection was used. Web's ten tests, lint/typecheck and production build
pass. Cached benchmark reports remain byte-identical; no model calls or label/cache
edits were needed. Final full-suite and CI results are recorded before handoff.

**Production planning remains held:** the 322-role / $9.66 figures below are the
September 28 pre-fix snapshot, not a verified count for the corrected UTC reader.
No production MCP database tools are available in this session. Under the owner's
"don't launch anything" instruction, no manual Actions workflow has been dispatched
for this round. Refresh the read-only production preflight before any later paid
launch; do not substitute the stale local SQLite copy or reuse the old plan hash.

## Launch Status

**Owner update, 2026-09-28:** drop the console-MTD seed. Once Cato clears this PR
and it merges, launch the single full backfill with the retained Actions ledger
and the unchanged **$30 cap**. Do not request a console number, replace the ledger,
raise the cap, or launch an unreviewed branch. Deliveroo Greenhouse stays excluded.
The earlier reconciliation prerequisite (ADR #103) is superseded by ADR #105;
seed inputs, receipt cache and month-specific cap overrides are removed.

**Further owner update:** the backfill window is now **14 days**, independently of
the unchanged 21-day browse/digest window. `recency_policy_v3.backfill_max_age_days`
controls both the full pass and daily 25-per-source trickle. Selection and actual
evaluation order are newest effective posting date first (posting date, otherwise
first-seen; descending ID for ties), before applying the source limit. Source
iteration remains unchanged: this is newest-first within each source queue, not
a cross-source queue redesign. Genuinely new/materially changed intake still uses
the existing 21-day policy. ADR #106 records this scope. The last read-only preflight
(before the UTC correction) selected **322 roles / $9.66 / 1h47m20s scoring**, with roughly **3.5-4.5 hours**
end-to-end including recent fetch/DB overhead. The 438-role figures below are
historical 21-day evidence, not the new launch estimate.

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

The last observed tracked MTD of $8.439607 plus the prior $13.14 backfill estimate
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
- Backfill now has its own validated 14-day config and newest-first selector/loop.
  It does not spend on policy-only re-evaluations aged 15-21 days; already-calibrated
  roles in that range remain browse/digest eligible under the unchanged age policy.
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

The v2 report identifies each source, exclusion reason, open posting IDs, all
owner-touched review/application records on that source, and a plan hash. Review
the entire report, including any previously disabled manual sources. The owner's
production path is **Actions -> Retire Inactive Sources -> Run workflow on main**,
with the exact reviewed `retirement_plan_hash`. The workflow regenerates the report
read-only before opening a writable connection and checks the hash again under
the lock. It never overlaps a scheduled scan. For an explicitly authorized local
operator with the production connection configured, the existing command remains:

```sh
job-agent retire-sources --apply-report output/source_retirement.json
```

Apply rechecks identity/current inactivity, new postings and touched history under
a short write lock. A stale/modified plan refuses; direct report replay changes
zero database rows, including source health. Actions rerun with an old consumed
hash refuses without writes because the fresh plan differs; approve a fresh empty
report to run an explicit no-op. It sets
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
6. The 14-day backfill cutoff is config-driven and shared with the planner; daily
   and full queues are newest-first before limiting. Test exact boundary, missing
   posted dates, scrambled IDs/evaluation timestamps, and the unchanged 21-day read.

Offline cached benchmarks pass unchanged: curated33 recall100%, precision94.7%,
blocker100%, exact20/33; uniform150 gate recall100%; gate-passer150 Apply/Consider
recall/precision100% (six positives), all-surfaced precision75%. These are historical
Claude-cache replays, not fresh paid prompt/profile calibration. Labels/caches unchanged.

Validation before the owner update: Python 3.12 full unittest suite passed (288 tests), followed by
22 focused tests after the final manual-source regression. Ruff and diff checks
pass. Web tests, lint, typecheck and production build pass; Profile JSON/YAML drift
checks pass. GitHub CI and the extended production preflight are recorded below
after the review branch is pushed. These builder checks do not replace Cato review.

## Historical 21-Day Production Evidence

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

## Historical 14-Day Preflight

Code: `54fad3c`. Read-only production
[run 36423901225](https://github.com/lasse-max/job-search-agent/actions/runs/36423901225)
completed successfully on 2026-09-28 at 12:48 UTC in 2m26s. The server reported
`transaction_read_only=on`; no evaluation or database write occurred. Policy:
`hybrid_claude_v4|candidate_profile_v4|location_policy_v5|scoring_policy_v2|recency_policy_v3`.

| Planning result | Count / estimate |
| --- | --- |
| Fresh current-source roles selected, within 14 days | 322 |
| Inactive-source roles selected | 0 |
| Inactive-source fresh stale candidates excluded | 5 |
| Of those, relevance-gate passers excluded | 1 |
| Scoring-only ETA | 6,440 seconds / 1h47m20s |
| Scoring-only spend estimate | $9.66 |
| End-to-end planning range including fetch/DB overhead | Roughly 3.5-4.5 hours |
| Reduction from prior 21-day plan | 116 roles / $3.48 / 38m40s scoring |

All five inactive candidates are from disabled Deliveroo Ashby. The all-age
retirement report is unchanged at 411 open postings: old Mistral Lever 172,
Black Forest Labs Greenhouse 17, Deliveroo Ashby 222. Its refreshed
[artifact](https://github.com/lasse-max/job-search-agent/actions/runs/36423901225/artifacts/10970244798)
is for owner/Cato inspection, not automatically applied.

Using the last observed tracked MTD (Sep27, $8.439607) plus $9.66 and the $3.30
remaining-scan reserve projects **$21.399607 tracked**, not a provider-bill total.
The ledger is not seeded or replaced and the cap stays $30. Refresh this plan at
dispatch if review/merge is delayed; dates can age out and normal scans can reduce
the queue. Deliveroo Greenhouse remains excluded.

Validation: all 288 Python tests and Ruff pass locally. Actual fake-provider call
order is tested for both 25/source and full backfills, including date boundaries,
null posted dates, scrambled IDs/evaluation timestamps, and config14-to7 behavior.
Web tests/lint/typecheck and Profile drift checks pass. All cached benchmark gates
pass with byte-identical reports; no paid benchmark calls or cache edits occurred.

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
